import streamlit as st
import pandas as pd
import mysql.connector
from datetime import date, datetime
import subprocess

# ===============================
# 1️⃣ Connect to MySQL
# ===============================
def connect_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="edt_examens"
    )

db = connect_db()
cursor = db.cursor(dictionary=True)

def query(sql: str) -> pd.DataFrame:
    cursor.execute(sql)
    return pd.DataFrame(cursor.fetchall())

# ===============================
# 2️⃣ Load Data
# ===============================
examens = query("""
    SELECT 
        g.nom AS groupe,
        m.nom AS module,
        COALESCE(p.nom, '❌ Not scheduled') AS prof,
        COALESCE(s.nom, '❌ Not scheduled') AS salle,
        COALESCE(e.date_exam, '❌ Not scheduled') AS date_exam,
        COALESCE(e.creneau_id, '❌ Not scheduled') AS creneau,
        f.id AS formation_id,
        f.nom AS formation,
        d.nom AS departement
    FROM groupes g
    JOIN modules m ON m.formation_id = g.formation_id
    JOIN formations f ON g.formation_id = f.id
    JOIN departements d ON f.dept_id = d.id
    LEFT JOIN examens e ON e.groupe_id = g.id AND e.module_id = m.id
    LEFT JOIN professeurs p ON e.prof_id = p.id
    LEFT JOIN lieu_examen s ON s.id = e.salle_id
""")

departements = query("SELECT * FROM departements")
formations = query("SELECT * FROM formations")
groupes = query("SELECT * FROM groupes")
profs = query("SELECT * FROM professeurs")
etudiant_groupe = query("SELECT * FROM etudiant_groupe")

# Convert date_exam to datetime
examens['date_exam'] = pd.to_datetime(examens['date_exam'], errors='coerce')

# ===============================
# 3️⃣ Sidebar: Role selection
# ===============================
st.sidebar.title("Select your role")
role = st.sidebar.selectbox(
    "Role",
    [
        "Vice-doyen et doyen",
        "Administrateur examens",
        "Chef de département",
        "Étudiants / Professeurs"
    ]
)

# ===============================
# 4️⃣ Dashboards by Role
# ===============================

# -------------------------------
# Vice-doyen et doyen: Strategic Global View
# -------------------------------
if role == "Vice-doyen et doyen":
    st.title("Vice-doyen et doyen – Vue stratégique globale")
    
    # Filter scheduled exams only
    scheduled = examens[examens['prof'] != '❌ Not scheduled'].copy()
    
    if scheduled.empty:
        st.info("⚠️ No exams are scheduled yet.")
    else:
        # ---------------------------
        # 1️⃣ Global Room & Hall Usage
        # ---------------------------
        st.subheader("Occupation globale des amphis et salles")
        
        # Count exams per room per date
        room_usage = scheduled.groupby(['date_exam', 'salle']).size().reset_index(name='exams_count')
        room_usage_pivot = room_usage.pivot(index='date_exam', columns='salle', values='exams_count').fillna(0)
        room_usage_pivot = room_usage_pivot.sort_index()
        
        st.bar_chart(room_usage_pivot)
        
        # Optional: total exams per room
        st.write("Total exams per room:")
        st.dataframe(room_usage.groupby('salle')['exams_count'].sum().sort_values(ascending=False))
        
        # ---------------------------
        # 2️⃣ Conflict Rate Per Department
        # ---------------------------
        st.subheader("Taux de conflits par département")
        
        def count_conflicts(df):
            # Conflict if the same group has more than 1 exam at the same date
            group_conflicts = df.duplicated(subset=['groupe','date_exam']).sum()
            prof_conflicts = df.duplicated(subset=['prof','date_exam']).sum()
            return pd.Series({
                "group_conflicts": group_conflicts,
                "prof_conflicts": prof_conflicts
            })
        
        conflicts = scheduled.groupby('departement').apply(count_conflicts).reset_index()
        st.dataframe(conflicts)
        
        st.bar_chart(conflicts.set_index('departement')[['group_conflicts', 'prof_conflicts']])
        
        # ---------------------------
        # 3️⃣ Academic KPIs
        # ---------------------------
        st.subheader("KPIs Académiques")
        
        total_exams = len(scheduled)
        distinct_profs = scheduled['prof'].nunique()
        distinct_groups = scheduled['groupe'].nunique()
        distinct_rooms = scheduled['salle'].nunique()
        total_hours_profs = scheduled.shape[0]  # Assuming each exam = 1 hour, can adjust if needed
        room_usage_rate = distinct_rooms / len(salles) if 'salles' in locals() else distinct_rooms  # Optional
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Exams Scheduled", total_exams)
        col1.metric("Distinct Groups", distinct_groups)
        
        col2.metric("Distinct Professors", distinct_profs)
        col2.metric("Total Professor Hours", total_hours_profs)
        
        col3.metric("Distinct Rooms Used", distinct_rooms)
        col3.metric("Room Usage Rate (%)", f"{room_usage_rate*100:.1f}")
        
        # ---------------------------
        # 4️⃣ Final Timetable Validation
        # ---------------------------
        st.subheader("Validation finale de l'EDT")
        if st.button("✅ Valider l'EDT"):
            st.success("📅 Timetable validated successfully by Vice-doyen et doyen")


# -------------------------------
# Administrateur examens
# -------------------------------
elif role == "Administrateur examens":
    st.title("Admin Dashboard - Gestion des examens")

    st.subheader("Exam Schedule")
    st.dataframe(examens)

    st.subheader("Actions")
    if st.button("Generate Timetable"):
        st.info("Generating timetable, this may take a few minutes...")
        subprocess.run(["python", "generate_timetable.py"])
        st.success("Timetable generated!")

    if st.button("Detect Conflicts"):
        scheduled = examens[examens['prof'] != '❌ Not scheduled']
        student_conflicts = scheduled.duplicated(subset=['groupe','date_exam']).sum()
        prof_conflicts = scheduled.duplicated(subset=['prof','date_exam']).sum()
        st.write(f"Student Conflicts: {student_conflicts}")
        st.write(f"Professor Conflicts: {prof_conflicts}")

    if st.button("Export CSV"):
        examens.to_csv("planning_examens_dashboard.csv", index=False)
        st.success("Exported to planning_examens_dashboard.csv")

# -------------------------------
# Chef de département
# -------------------------------
elif role == "Chef de département":
    st.title("Department Head Dashboard")

    dept_list = examens['departement'].dropna().unique()
    dept = st.selectbox("Select department", dept_list)
    dept_examens = examens[examens['departement'] == dept]

    formation_list = dept_examens['formation'].dropna().unique()
    formation = st.selectbox("Select formation", formation_list)
    formation_examens = dept_examens[dept_examens['formation'] == formation]

    st.subheader(f"Exams for {formation} ({dept})")
    st.dataframe(formation_examens)

    # KPIs
    st.metric("Total Exams", len(formation_examens))
    st.metric("Distinct Groups", formation_examens['groupe'].nunique())
    st.metric("Distinct Professors", formation_examens[formation_examens['prof'] != '❌ Not scheduled']['prof'].nunique())
    st.metric("Conflicts", formation_examens.duplicated(subset=['groupe','date_exam']).sum())

# -------------------------------
# Étudiants / Professeurs
# -------------------------------
elif role == "Étudiants / Professeurs":
    st.title("Personalized Exam View")

    user_type = st.radio("I am a", ["Student", "Professor"])

    if user_type == "Professor":
        prof_list = examens[examens['prof'] != '❌ Not scheduled']['prof'].unique()
        prof_name = st.selectbox("Select professor", prof_list)
        prof_examens = examens[examens['prof'] == prof_name].sort_values('date_exam')
        st.dataframe(prof_examens)
    else:
        group_list = examens['groupe'].unique()
        group_name = st.selectbox("Select your group", group_list)
        student_examens = examens[examens['groupe'] == group_name].sort_values('date_exam')
        st.dataframe(student_examens)
