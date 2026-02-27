# prosthesis_app.py
import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Prosthesis Sizing Tool", page_icon="🦾", layout="centered")

st.title("🦾 Upper Limb Prosthesis Sizing Tool")
st.write("Enter patient measurements below to receive the recommended prosthesis size.")

# --- Input fields ---
patient_name = st.text_input("Patient Name")
residual_length = st.number_input("Residual limb length (mm)", min_value=50, max_value=400, step=1)
forearm_circumference = st.number_input("Forearm circumference (mm)", min_value=40, max_value=400, step=1)
biceps_circumference = st.number_input("Biceps circumference (mm)", min_value=50, max_value=500, step=1)

# --- Processing logic (placeholder) ---
def calculate_prosthesis_size(residual, forearm, biceps):
    # Replace with your parametric model equations
    base_size = (residual * 0.4) + (forearm * 0.35) + (biceps * 0.25)
    
    if base_size < 150:
        category = "Small"
    elif base_size < 250:
        category = "Medium"
    else:
        category = "Large"
        
    return round(base_size, 2), category

# --- Button ---
if st.button("Calculate Recommended Size"):
    size_value, size_category = calculate_prosthesis_size(residual_length, forearm_circumference, biceps_circumference)
    
    st.success(f"Recommended prosthesis size: **{size_value} mm**")
    st.info(f"Suggested category: **{size_category}**")

    # --- Save to CSV ---
    record = {
        "Patient Name": patient_name,
        "Residual Limb Length (mm)": residual_length,
        "Forearm Circumference (mm)": forearm_circumference,
        "Biceps Circumference (mm)": biceps_circumference,
        "Recommended Size (mm)": size_value,
        "Category": size_category
    }
    
    file_path = "prosthesis_records.csv"
    
    # If file exists, append, else create
    if os.path.exists(file_path):
        df_existing = pd.read_csv(file_path)
        df = pd.concat([df_existing, pd.DataFrame([record])], ignore_index=True)
    else:
        df = pd.DataFrame([record])
    
    df.to_csv(file_path, index=False)
    st.success(f"✅ Record saved to `{file_path}`")

    # --- Optional download button for current record ---
    st.download_button(
        "Download this patient's record",
        data=pd.DataFrame([record]).to_csv(index=False),
        file_name=f"{patient_name}_prosthesis_record.csv",
        mime="text/csv"
    )