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
This tool extracts sold volume (MBF) totals and displays them separated by year and region.
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
        return None, "No table data found in PDF"

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
        return None, f"No sold volume column found. Columns detected: {', '.join(df.columns.tolist())}"

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

    if df.empty:
        return None, "Sold volume column found but contained no valid numeric data"

    # ----------------------------
    # Parse year and region from filename
    # ----------------------------
    filename_year = parse_year(uploaded_file.name)
    region = parse_region(uploaded_file.name)

    result = df[[sold_col]].copy()
    result.columns = ["Sold Volume (MBF)"]
    result["Year"] = filename_year if filename_year else "Unknown"
    result["Region"] = region

    return result[["Region", "Year", "Sold Volume (MBF)"]], None


# ----------------------------
# MAIN PROCESS
# ----------------------------
if uploaded_files:
    all_results = []
    skipped = []

    for uploaded_file in uploaded_files:
        with st.spinner(f"Processing {uploaded_file.name}..."):
            result, error = extract_sold_volume(uploaded_file)
            region = parse_region(uploaded_file.name)
            year = parse_year(uploaded_file.name)

            if result is None:
                st.warning(f"⚠️ Skipped `{uploaded_file.name}`: {error}")
                skipped.append({"File": uploaded_file.name, "Reason": error})
            else:
                year_label = str(year) if year else "Unknown Year"
                st.success(f"✅ `{uploaded_file.name}` → **{region}** | **{year_label}** — {len(result)} rows extracted")
                all_results.append(result)

    if skipped:
        with st.expander("⚠️ Skipped files — click to expand"):
            st.dataframe(pd.DataFrame(skipped))

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)

        # Aggregate to one total per region per year
        combined = combined.groupby(["Year", "Region"], as_index=False)["Sold Volume (MBF)"].sum()
        combined = combined.sort_values(["Year", "Region"]).reset_index(drop=True)

        # ----------------------------
        # 📄 COMBINED DATA TABLE
        # ----------------------------
        st.subheader("📄 Combined Sold Volume Data")

        # Filter by year — safely handles mixed int/"Unknown" types
        years_available = sorted(combined["Year"].unique(), key=lambda x: (str(x) == "Unknown", x))
        selected_years = st.multiselect(
            "Filter by year (leave blank to show all):",
            options=years_available,
            default=years_available
        )
        filtered = combined[combined["Year"].isin(selected_years)]
        st.dataframe(filtered)

        # ----------------------------
        # 📊 PIVOT TABLE — rows = Year, columns = Region
        # ----------------------------
        st.subheader("📊 Sold Volume (MBF) by Year & Region (Pivot)")
        pivot = filtered.pivot_table(
            index="Year",
            columns="Region",
            values="Sold Volume (MBF)",
            aggfunc="sum"
        )
        pivot["Grand Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_index()
        st.dataframe(pivot.style.format("{:,.2f}"))

        # ----------------------------
        # 📈 CHART — each region is its own line, x axis = year
        # ----------------------------
        st.subheader("📈 Sold Volume (MBF) Over Time by Region")
        chart_data = pivot.drop(columns=["Grand Total"])
        st.line_chart(chart_data)

        # ----------------------------
        # ⚠️ DATA QUALITY REPORT
        # ----------------------------
        st.subheader("⚠️ Data Quality Report")
        st.write(f"Files processed: {len(all_results)}")
        st.write(f"Files skipped: {len(skipped)}")
        st.write(f"Years found: {', '.join(str(y) for y in years_available)}")
        st.write(f"Regions found: {', '.join(sorted(combined['Region'].unique()))}")
        st.write(f"Total rows: {len(combined)}")
        missing = combined.isnull().sum().sum()
        if missing == 0:
            st.success("No missing values detected!")
        else:
            st.write(f"Missing values: {missing}")
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
