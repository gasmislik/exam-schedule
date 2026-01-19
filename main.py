import mysql.connector
from datetime import date, timedelta
from collections import defaultdict
import csv
import time

def connect_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="edt_examens"
    )

db = connect_db()
cursor = db.cursor(dictionary=True)

def load(sql):
    cursor.execute(sql)
    return cursor.fetchall()

 modules = load("SELECT * FROM modules")
groupes = load("SELECT * FROM groupes")
formations = load("SELECT * FROM formations")
profs = load("SELECT * FROM professeurs")
salles = load("SELECT * FROM lieu_examen ORDER BY capacite DESC")
creneaux = load("SELECT * FROM creneaux ORDER BY id")[:4]
etudiant_groupes = load("SELECT * FROM etudiant_groupe")

formation_name = {f["id"]: f["nom"] for f in formations}

group_size = defaultdict(int)
for eg in etudiant_groupes:
    group_size[eg["groupe_id"]] += 1

START_DATE = date(2025, 1, 10)
NB_DAYS = 20
 DUREE = 90

student_day = {}         
prof_day = defaultdict(int)  
prof_total = defaultdict(int) 
room_usage = set()       


def available_profs(exam_date):
    """Retourne la liste des profs disponibles, triée par le moins d'examens total"""
    profs_ok = [p for p in profs if prof_day[(p["id"], exam_date)] < 3]
    return sorted(profs_ok, key=lambda p: prof_total[p["id"]])

def available_rooms(group_id, exam_date, creneau_id):
    """Retourne les salles disponibles pour un groupe donné à une date et créneau"""
    size = group_size[group_id]
    result = []

    for s in salles:
        if s["type"] == "Salle":
            if (s["id"],  exam_date, creneau_id) not in room_usage and size <= s["capacite"]:
                result.append(s)
        else: 
            count = sum(
                1 for r in room_usage
                if len(r) == 4 and r[0] == s["id"] and r[1] == exam_date and r[2] == creneau_id
            )
             if count < 2:
                result.append(s)
    return result


from random import shuffle

def generate_schedule_complete():
    inserted = 0
    non_planifies = []

    for g in groupes:
        group_modules = [m for m in modules if m["formation_id"] == g["formation_id"]]
        if not group_modules:
            non_planifies.append((g["nom"], "aucun module"))
            continue

        for m in group_modules:
            placed = False
               for d in range(NB_DAYS):
                exam_date = START_DATE + timedelta(days=d)
                if student_day.get((g["id"], exam_date)):
                    continue

                shuffled_creneaux = creneaux.copy()
                shuffle(shuffled_creneaux)

                for c in shuffled_creneaux:
                    rooms = available_rooms(g["id"], exam_date, c["id"])
                    if not rooms:
                        continue

                    profs_ok = available_profs(exam_date)
                    if not profs_ok:
                        continue

                    prof = profs_ok[0]
                    salle = rooms[0]
                    exam_date_str = exam_date.strftime('%Y-%m-%d')

                    try:
                        cursor.execute("""
                            INSERT INTO examens
                            (module_id, groupe_id, prof_id, salle_id, date_exam, creneau_id, duree_minutes)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """, (m["id"], g["id"], prof["id"], salle["id"], exam_date_str, c["id"], DUREE))
                        db.commit()
                     except Exception as e:
                        print(f" Erreur INSERT pour groupe {g['nom']}, module {m['nom']}: {e}")
                        continue

                    student_day[(g["id"], exam_date)] = 1
                    prof_day[(prof["id"], exam_date)] += 1
                    prof_total[prof["id"]] += 1

                    if salle["type"] == "Amphi":
                        room_usage.add((salle["id"], exam_date, c["id"], g["id"]))
                    else:
                        room_usage.add((salle["id"], exam_date, c["id"]))

                    print(f"PLANIFIE: Groupe {g['nom']} | Module {m['nom']} | Salle {salle['nom']} | Prof {prof['nom']} | Date {exam_date_str} | Creneau {c['id']}")
                    inserted += 1
                    placed = True
                    break  

                if placed:
                    break 

            if not placed:
                non_planifies.append((g["nom"], m["nom"]))
                print(f"Module {m['nom']} du Groupe {g['nom']} NON PLANIFIÉ")

    return inserted, non_planifies


def detect_conflicts():
    profs_conflict = [p for (p,d), cnt in prof_day.items() if cnt > 3]
    students_conflict = sum(1 for v in student_day.values() if v>1)
    return students_conflict, profs_conflict

def export_csv():
    cursor.execute("""
        SELECT e.id as exam_id, g.nom as groupe, m.nom as module, p.nom as prof, s.nom as salle, e.date_exam, e.creneau_id
        FROM examens e
        JOIN groupes g ON e.groupe_id = g.id
        JOIN modules m ON e.module_id=m.id
        JOIN professeurs p ON e.prof_id=p.id
        JOIN lieu_examen s ON e.salle_id=s.id
    """)
    rows = cursor.fetchall()
    with open("planning_examens.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Exam ID", "Groupe", "Module", "Prof", "Salle", "Date", "Creneau"])
        for r in rows:
            writer.writerow([r["exam_id"], r["groupe"], r["module"], r["prof"], r["salle"], r["date_exam"], r["creneau_id"]])

if __name__ == "__main__":
    start = time.time()
    inserted, non_planifies = generate_schedule_complete()
    print(f"\n[OK] {inserted} examens planifiés")
    if non_planifies:
        print("\nModules non planifiés :", non_planifies)
    else:
        print("\nTous les modules ont été planifiés")

    students_conflict, profs_conflict = detect_conflicts()
    if students_conflict or profs_conflict:
        print("\nConflits détectés :")
        print("Étudiants :", students_conflict)
        print("Profs :", profs_conflict)
    else:
        print("\nAucun conflit détecté")

    export_csv()
    print("\nPlanning exporté dans planning_examens.csv")
    print("Execution time:", round(time.time()-start, 2), "sec")
