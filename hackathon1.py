import streamlit as st
import pdfplumber
import pandas as pd
import re

# ----------------------------
# APP TITLE
# ----------------------------
st.title("🌲 ForestData Cleaner")
st.markdown("""
Upload USDA timber sales PDF data.  
This tool extracts sold volume totals and displays them in a combined chart across all uploaded files.
""")

uploaded_files = st.file_uploader("Upload Timber Sales PDFs", type="pdf", accept_multiple_files=True)

# ----------------------------
# HELPER: Extract sold volume from a single PDF
# ----------------------------
def extract_sold_volume(uploaded_file):
    all_rows = []

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                all_rows.extend(table)

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)

    # Fix header
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

    # Drop fully empty columns
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    # ----------------------------
    # Find the sold volume column
    # ----------------------------
    sold_col = None
    for col in df.columns:
        if re.search(r"sold.{0,10}vol", col, re.IGNORECASE):
            sold_col = col
            break

    # Fallback: look for any column with "volume" in the name
    if not sold_col:
        for col in df.columns:
            if "volume" in col.lower():
                sold_col = col
                break

    # Fallback: look for any column with "sold" in the name
    if not sold_col:
        for col in df.columns:
            if "sold" in col.lower():
                sold_col = col
                break

    if not sold_col:
        return None

    # ----------------------------
    # Find the year column
    # ----------------------------
    year_col = None
    for col in df.columns:
        if re.search(r"year|date|fy|fiscal", col, re.IGNORECASE):
            year_col = col
            break

    # Clean the sold volume column
    def clean_numeric(x):
        try:
            if isinstance(x, (list, tuple)):
                x = " ".join(map(str, x))
            x = str(x).replace(",", "").strip()
            if x in ["", "None", "nan"]:
                return None
            return float(x)
        except Exception:
            return None

    df[sold_col] = df[sold_col].apply(clean_numeric)
    df = df.dropna(subset=[sold_col])

    # ----------------------------
    # Build result: year + sold volume
    # ----------------------------
    if year_col:
        df[year_col] = df[year_col].astype(str).str.strip()
        result = df[[year_col, sold_col]].copy()
        result.columns = ["Year", "Sold Volume"]
        result["Year"] = pd.to_numeric(result["Year"], errors="coerce")
        result = result.dropna(subset=["Year"])
        result["Year"] = result["Year"].astype(int)
    else:
        # No year column — use row index as a sequence
        result = df[[sold_col]].copy()
        result.columns = ["Sold Volume"]
        result["Year"] = result.index + 1

    result["Source File"] = uploaded_file.name
    return result[["Source File", "Year", "Sold Volume"]]


# ----------------------------
# MAIN PROCESS
# ----------------------------
if uploaded_files:
    all_results = []

    for uploaded_file in uploaded_files:
        with st.spinner(f"Processing {uploaded_file.name}..."):
            result = extract_sold_volume(uploaded_file)
            if result is None:
                st.warning(f"⚠️ Could not extract sold volume from `{uploaded_file.name}`. Skipping.")
            else:
                st.success(f"✅ Extracted {len(result)} rows from `{uploaded_file.name}`")
                all_results.append(result)

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)

        # ----------------------------
        # 📄 COMBINED DATA TABLE
        # ----------------------------
        st.subheader("📄 Combined Sold Volume Data")
        st.dataframe(combined)

        # ----------------------------
        # 📊 PIVOT TABLE (matches your Excel layout)
        # ----------------------------
        st.subheader("📊 Sold Volume by Year (Pivot)")
        pivot = combined.pivot_table(
            index="Year",
            columns="Source File",
            values="Sold Volume",
            aggfunc="sum"
        )
        pivot["Grand Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_index()
        st.dataframe(pivot.style.format("{:,.2f}"))

        # ----------------------------
        # 📈 CHART
        # ----------------------------
        st.subheader("📈 Sold Volume Over Time")
        st.line_chart(pivot.drop(columns=["Grand Total"]))

        # ----------------------------
        # ⚠️ DATA QUALITY REPORT
        # ----------------------------
        st.subheader("⚠️ Data Quality Report")
        st.write(f"Files processed: {len(all_results)}")
        st.write(f"Total rows extracted: {len(combined)}")
        missing = combined.isnull().sum().sum()
        st.write(f"Missing values: {missing}")
        if missing == 0:
            st.success("No missing values detected!")

        # ----------------------------
        # 💾 DOWNLOADS
        # ----------------------------
        st.subheader("💾 Downloads")

        csv_combined = combined.to_csv(index=False).encode("utf-8")
        st.download_button(
            "💾 Download Raw Combined Data (CSV)",
            csv_combined,
            "sold_volume_combined.csv",
            "text/csv"
        )

        csv_pivot = pivot.to_csv().encode("utf-8")
        st.download_button(
            "💾 Download Pivot Table (CSV)",
            csv_pivot,
            "sold_volume_pivot.csv",
            "text/csv"
        )
