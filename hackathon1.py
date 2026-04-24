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
This tool extracts sold volume (MBF) totals and displays them in a combined chart across all regions.
""")

uploaded_files = st.file_uploader("Upload Timber Sales PDFs", type="pdf", accept_multiple_files=True)

# ----------------------------
# HELPER: Parse region from filename
# e.g. "2025-q4-cut-sold-r01.pdf" → "Region 01"
# ----------------------------
def parse_region(filename):
    match = re.search(r'r(\d+)', filename, re.IGNORECASE)
    if match:
        return f"Region {match.group(1).zfill(2)}"
    return filename

# ----------------------------
# HELPER: Parse year from filename
# e.g. "2025-q4-cut-sold-r01.pdf" → 2025
# ----------------------------
def parse_year(filename):
    match = re.search(r'\b(19|20)\d{2}\b', filename)
    if match:
        return int(match.group(0))
    return None

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
    # Find the sold volume column — prioritize MBF
    # ----------------------------
    sold_col = None
    # 1st priority: sold volume MBF
    for col in df.columns:
        if re.search(r"sold.{0,20}mbf", col, re.IGNORECASE):
            sold_col = col
            break
    # 2nd priority: any MBF column
    if not sold_col:
        for col in df.columns:
            if "mbf" in col.lower():
                sold_col = col
                break
    # 3rd priority: sold + volume together
    if not sold_col:
        for col in df.columns:
            if re.search(r"sold.{0,10}vol", col, re.IGNORECASE):
                sold_col = col
                break
    # 4th priority: any volume column
    if not sold_col:
        for col in df.columns:
            if "volume" in col.lower():
                sold_col = col
                break
    # 5th priority: any sold column
    if not sold_col:
        for col in df.columns:
            if "sold" in col.lower():
                sold_col = col
                break
    if not sold_col:
        return None
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
    # Year and region from filename
    # ----------------------------
    region = parse_region(uploaded_file.name)
    year = parse_year(uploaded_file.name)
    result = df[[sold_col]].copy()
    result.columns = ["Sold Volume (MBF)"]
    result["Year"] = year if year else "Unknown"
    result["Region"] = region
    return result[["Region", "Year", "Sold Volume (MBF)"]]

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
                region = parse_region(uploaded_file.name)
                year = parse_year(uploaded_file.name)
                year_label = str(year) if year else "Unknown Year"
                st.success(f"✅ `{uploaded_file.name}` → **{region}** | **{year_label}** — {len(result)} rows extracted")
                all_results.append(result)
    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        combined = combined.groupby(["Year", "Region"], as_index=False)["Sold Volume (MBF)"].sum()
        combined = combined.iloc[
            sorted(range(len(combined)), key=lambda i: (
                str(combined.iloc[i]["Year"]) == "Unknown",
                str(combined.iloc[i]["Year"]),
                combined.iloc[i]["Region"]
            ))
        ].reset_index(drop=True)
        # ----------------------------
        # 📄 COMBINED DATA TABLE
        # ----------------------------
        st.subheader("📄 Combined Sold Volume Data")
        years_available = sorted(
            combined["Year"].unique(),
            key=lambda x: (str(x) == "Unknown", x)
        )
        selected_years = st.multiselect(
            "Filter by year (leave blank to show all):",
            options=years_available,
            default=years_available
        )
        filtered = combined[combined["Year"].isin(selected_years)]
        st.dataframe(filtered)
        # ----------------------------
        # 📊 PIVOT TABLE
        # ----------------------------
        st.subheader("📊 Sold Volume (MBF) by Year & Region (Pivot)")
        pivot = filtered.pivot_table(
            index="Year",
            columns="Region",
            values="Sold Volume (MBF)",
            aggfunc="sum"
        )
        pivot["Grand Total"] = pivot.sum(axis=1)
        pivot = pivot.iloc[
            sorted(range(len(pivot)), key=lambda i: (
                str(pivot.index[i]) == "Unknown",
                str(pivot.index[i])
            ))
        ]
        st.dataframe(pivot.style.format("{:,.2f}"))
        # ----------------------------
        # 📈 CHART
        # ----------------------------
        st.subheader("📈 Sold Volume (MBF) Over Time by Region")
        st.line_chart(pivot.drop(columns=["Grand Total"]))
        # ----------------------------
        # ⚠️ DATA QUALITY REPORT
        # ----------------------------
        st.subheader("⚠️ Data Quality Report")
        st.write(f"Files processed: {len(all_results)}")
        st.write(f"Years found: {', '.join(str(y) for y in years_available)}")
        st.write(f"Regions found: {', '.join(sorted(combined['Region'].unique()))}")
        st.write(f"Total rows extracted: {len(combined)}")
        missing = combined.isnull().sum().sum()
        st.write(f"Missing values: {missing}")
        if missing == 0:
            st.success("No missing values detected!")
        else:
            st.write("Columns with issues:")
            st.write(combined.isnull().sum()[combined.isnull().sum() > 0])
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
