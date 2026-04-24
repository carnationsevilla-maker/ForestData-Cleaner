import streamlit as st
import pdfplumber
import pandas as pd

# ----------------------------
# APP TITLE
# ----------------------------
st.title("🌲 ForestData Cleaner")

st.markdown("""
Upload USDA timber sales PDF data.  
This tool extracts, cleans, and converts it into Excel-ready format while flagging data issues.
""")

uploaded_file = st.file_uploader("Upload Timber Sales PDF", type="pdf")

# ----------------------------
# MAIN PROCESS
# ----------------------------
if uploaded_file:

    all_rows = []

    # ----------------------------
    # 1. Extract PDF tables
    # ----------------------------
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                all_rows.extend(table)

    # Safety check
    if not all_rows:
        st.error("No table data found in this PDF.")
        st.stop()

    # ----------------------------
    # 2. Create DataFrame
    # ----------------------------
    df = pd.DataFrame(all_rows)

    # ----------------------------
    # 3. Fix header row
    # ----------------------------
    df.columns = df.iloc[0]
    df = df[1:]

    # ----------------------------
    # 4. Clean structure
    # ----------------------------
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    # Rename first column to Forest
    df = df.rename(columns={df.columns[0]: "Forest"})
    df["Forest"] = df["Forest"].astype(str).str.strip()

    # ----------------------------
    # 5. FINAL SAFE CLEANING
    # ----------------------------
    def clean_value(x):
        try:
            # Handle weird list/tuple values from PDF
            if isinstance(x, (list, tuple)):
                x = " ".join(map(str, x))

            # Convert everything to string
            x = str(x)

            # Remove commas and spaces
            x = x.replace(",", "").strip()

            # Handle empty or invalid values
            if x in ["", "None", "nan"]:
                return None

            return x

        except Exception:
            return None

    for col in df.columns:
        if col != "Forest":
            df[col] = df[col].apply(clean_value)
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.reset_index(drop=True)

    # ----------------------------
    # 📄 RAW DATA
    # ----------------------------
    st.subheader("📄 Raw Extracted Data")
    st.dataframe(df)

    # ----------------------------
    # ⚠️ DATA QUALITY REPORT
    # ----------------------------
    st.subheader("⚠️ Data Quality Report")

    missing_values = df.isnull().sum().sum()
    total_values = df.size
    missing_percent = (missing_values / total_values) * 100

    st.write(f"Total missing values: {missing_values}")
    st.write(f"Missing data percentage: {missing_percent:.2f}%")

    if missing_values > 0:
        st.write("Columns with issues:")
        st.write(df.isnull().sum()[df.isnull().sum() > 0])
    else:
        st.success("No missing values detected!")

    # ----------------------------
    # 📊 VISUALIZATION
    # ----------------------------
    st.subheader("📊 Timber Trends Preview")

    numeric_df = df.select_dtypes(include="number")

    if not numeric_df.empty:
        st.line_chart(numeric_df)
    else:
        st.write("No numeric data available for visualization.")

    # ----------------------------
    # 💾 DOWNLOAD
    # ----------------------------
    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "💾 Download Clean Data (CSV)",
        csv,
        "forest_clean_data.csv",
        "text/csv"
    )
