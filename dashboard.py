import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime
import subprocess

def connect_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="edt_examens"
    )

db = connect_db()
cursor = db.cursor(dictionary=True)

def run_query(sql):
    cursor.execute(sql)
    return pd.DataFrame(cursor.fetchall())

examens = run_query("""
    SELECT 
        g.nom AS groupe,
        m.nom AS module,
        COALESCE(p.nom, 'Not scheduled') AS prof,
        COALESCE(s.nom, 'Not scheduled') AS salle,
        e.date_exam,
        f.nom AS formation,
        d.nom AS departement
    FROM groupes g
    JOIN modules m ON m.formation_id = g.formation_id
    JOIN formations f ON g.formation_id = f.id
    JOIN departements d ON f.dept_id = d.id
    LEFT JOIN examens e ON e.groupe_id = g.id AND e.module_id = m.id
    LEFT JOIN professeurs p ON e.prof_id = p.id
    LEFT JOIN lieu_examen s ON e.salle_id = s.id
""")

examens["date_exam"] = pd.to_datetime(examens["date_exam"], errors="coerce")

st.sidebar.title("User role")

role = st.sidebar.selectbox(
    "Choose your role",
    [
        "Vice Dean / Dean",
        "Exam Administrator",
        "Department Head",
        "Student / Professor"
    ]
   )

if role == "Vice Dean / Dean":
    st.title("Global Overview of Exam Planning")

    scheduled = examens[examens["prof"] != "Not scheduled"]

    if scheduled.empty:
        st.warning("No exams have been scheduled yet.")
    else:
        st.subheader("Room usage per day")

        room_usage = (
            scheduled
            .groupby(["date_exam", "salle"])
            .size()
            .reset_index(name="count")
        )

        pivot = room_usage.pivot(
            index="date_exam",
            columns="salle",
            values="count"
        ).fillna(0)

        st.bar_chart(pivot)

        st.subheader("Conflicts by department")

        def detect_conflicts(df):
            group_conflicts = df.duplicated(
                subset=["groupe", "date_exam"]
            ).sum()

            prof_conflicts = df.duplicated(
                subset=["prof", "date_exam"]
            ).sum()

            return pd.Series({
                "Group conflicts": group_conflicts,
                "Professor conflicts": prof_conflicts
            })

        conflicts = scheduled.groupby("departement").apply(detect_conflicts)
        st.dataframe(conflicts)

        st.subheader("Key indicators")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total exams", len(scheduled))
        col2.metric("Professors involved", scheduled["prof"].nunique())
        col3.metric("Groups involved", scheduled["groupe"].nunique())

        if st.button("Validate timetable"):
            st.success("Timetable validated successfully.")

elif role == "Exam Administrator":
    st.title("Exam Administration")

    st.subheader("All exams")
    st.dataframe(examens)

    if st.button("Generate timetable"):
        subprocess.run(["python", "generate_timetable.py"])
        st.success("Timetable generated.")

    if st.button("Detect conflicts"):
        scheduled = examens[examens["prof"] != "Not scheduled"]

        student_conflicts = scheduled.duplicated(
            subset=["groupe", "date_exam"]
        ).sum()

        prof_conflicts = scheduled.duplicated(
            subset=["prof", "date_exam"]
        ).sum()

        st.write("Student conflicts:", student_conflicts)
        st.write("Professor conflicts:", prof_conflicts)

    if st.button("Export to CSV"):
        examens.to_csv("exam_planning.csv", index=False)
        st.success("File exported.")


elif role == "Department Head":
    st.title("Department View")

    dept = st.selectbox(
        "Select department",
        examens["departement"].dropna().unique()
    )

    dept_data = examens[examens["departement"] == dept]

    formation = st.selectbox(
        "Select formation",
        dept_data["formation"].dropna().unique()
    )

    data = dept_data[dept_data["formation"] == formation]

    st.dataframe(data)

    st.metric("Total exams", len(data))
    st.metric("Groups", data["groupe"].nunique())
    st.metric("Professors", data["prof"].nunique())

else:
    st.title("Personal Exam Schedule")

    user_type = st.radio("I am a", ["Student", "Professor"])

    if user_type == "Professor":
        prof = st.selectbox(
            "Choose your name",
            examens[examens["prof"] != "Not scheduled"]["prof"].unique()
        )
        st.dataframe(
            examens[examens["prof"] == prof].sort_values("date_exam")
        )
    else:
        group = st.selectbox(
            "Choose your group",
            examens["groupe"].unique()
        )
        st.dataframe(
            examens[examens["groupe"] == group].sort_values("date_exam")
        )
