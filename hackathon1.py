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

uploaded_files = st.file_uploader("Upload Timber Sales PDFs", type="pdf", accept_multiple_files=True)

# ----------------------------
# MAIN PROCESS
# ----------------------------
if uploaded_files:
    all_dfs = []

    for uploaded_file in uploaded_files:
        st.markdown(f"---\n### 📁 Processing: `{uploaded_file.name}`")
        all_rows = []

        # ----------------------------
        # 1. Extract PDF tables
        # ----------------------------
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    all_rows.extend(table)

        if not all_rows:
            st.warning(f"No table data found in {uploaded_file.name}. Skipping.")
            continue

        # ----------------------------
        # 2. Create DataFrame
        # ----------------------------
        df = pd.DataFrame(all_rows)

        # ----------------------------
        # 3. Fix header row — SAFE VERSION
        # ----------------------------
        header = df.iloc[0].tolist()

        header = [
            " ".join(map(str, h)) if isinstance(h, (list, tuple)) else str(h).strip()
            for h in header
        ]

        seen = {}
        clean_header = []
        for h in header:
            if h in ("", "None", "nan"):
                h = f"col_{len(clean_header)}"
            if h in seen:
                seen[h] += 1
                h = f"{h}_{seen[h]}"
            else:
                seen[h] = 0
            clean_header.append(h)

        df.columns = clean_header
        df = df[1:].reset_index(drop=True)

        # ----------------------------
        # 4. Clean structure
        # ----------------------------
        df = df.dropna(axis=1, how="all")
        df.columns = [str(c).strip() for c in df.columns]

        df = df.rename(columns={df.columns[0]: "Forest"})
        df["Forest"] = df["Forest"].astype(str).str.strip()

        # Tag which file this row came from
        df.insert(0, "Source File", uploaded_file.name)

        # ----------------------------
        # 5. FINAL SAFE CLEANING
        # ----------------------------
        def clean_value(x):
            try:
                if isinstance(x, (list, tuple)):
                    x = " ".join(map(str, x))
                x = str(x)
                x = x.replace(",", "").strip()
                if x in ["", "None", "nan"]:
                    return None
                return x
            except Exception:
                return None

        for col in df.columns:
            if col not in ("Forest", "Source File"):
                df[col] = df[col].apply(clean_value)
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.reset_index(drop=True)

        # ----------------------------
        # 📄 RAW DATA (per file)
        # ----------------------------
        st.subheader("📄 Extracted Data")
        st.dataframe(df)

        # ----------------------------
        # ⚠️ DATA QUALITY REPORT (per file)
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
        # 📊 VISUALIZATION (per file)
        # ----------------------------
        st.subheader("📊 Timber Trends Preview")
        numeric_df = df.select_dtypes(include="number")
        if not numeric_df.empty:
            st.line_chart(numeric_df)
        else:
            st.write("No numeric data available for visualization.")

        all_dfs.append(df)

    # ----------------------------
    # 💾 COMBINED DOWNLOAD
    # ----------------------------
    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        st.markdown("---")
        st.subheader("💾 Download All Files Combined")
        csv = combined_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "💾 Download Combined Clean Data (CSV)",
            csv,
            "forest_clean_data_combined.csv",
            "text/csv"
        )
