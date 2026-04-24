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
# ----------------------------
def parse_region(filename):
    match = re.search(r'r(\d+)', filename, re.IGNORECASE)
    if match:
        return f"Region {match.group(1).zfill(2)}"
    return filename

# ----------------------------
# HELPER: Parse year from filename
# ----------------------------
def parse_year(filename):
    match = re.search(r'\b(19|20)\d{2}\b', filename)
    if match:
        return int(match.group(0))
    return None

# ----------------------------
# HELPER: Clean a numeric string
# ----------------------------
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

# ----------------------------
# HELPER: Extract sold volume (MBF) from total row
# Strategy: find the "Region (...) Total" row in raw PDF text,
# then parse the numbers that follow in order:
# Total : [num_sales] [sold_vol_mbf] [sold_vol_ccf] [sold_value] [cut_value]
# We want index 1 (sold volume MBF) after num_sales
# ----------------------------
def extract_sold_volume(uploaded_file):
    full_text = ""

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text:
        return None, "No text found in PDF"

    # Find the Region Total line
    # e.g. "Region (R1, Northern Region) Total :  12,989  279,452.37  539,668.22 ..."
    total_match = re.search(
        r'Region\s*\(.*?\)\s*Total\s*:?\s*([\d,]+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )

    if total_match:
        # Group 1 = num sales, Group 2 = Sold Volume (MBF), Group 3 = Sold Volume (CCF)
        raw_mbf = total_match.group(2)
        val = clean_numeric(raw_mbf)
        if val is not None:
            region = parse_region(uploaded_file.name)
            year = parse_year(uploaded_file.name)
            result = pd.DataFrame([{
                "Region": region,
                "Year": year if year else "Unknown",
                "Sold Volume (MBF)": val
            }])
            return result[["Region", "Year", "Sold Volume (MBF)"]], None

    # ----------------------------
    # Fallback: scan all lines for any "Total" line with numbers
    # ----------------------------
    for line in full_text.splitlines():
        if re.search(r'total', line, re.IGNORECASE):
            numbers = re.findall(r'[\d,]+\.?\d*', line)
            numbers = [clean_numeric(n) for n in numbers]
            numbers = [n for n in numbers if n is not None]
            # Skip the first number if it looks like a sale count (no decimal)
            # and grab the next one as MBF
            if len(numbers) >= 2:
                for n in numbers:
                    if n != int(n):  # first decimal number = MBF
                        val = n
                        region = parse_region(uploaded_file.name)
                        year = parse_year(uploaded_file.name)
                        result = pd.DataFrame([{
                            "Region": region,
                            "Year": year if year else "Unknown",
                            "Sold Volume (MBF)": val
                        }])
                        return result[["Region", "Year", "Sold Volume (MBF)"]], f"Used fallback total line: '{line.strip()}'"

    return None, "Could not find a Region Total line in this PDF"


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
                vol = result["Sold Volume (MBF)"].iloc[0]
                if error:
                    st.warning(f"⚠️ `{uploaded_file.name}` → **{region}** | **{year_label}** — {vol:,.2f} MBF (fallback used)")
                else:
                    st.success(f"✅ `{uploaded_file.name}` → **{region}** | **{year_label}** — {vol:,.2f} MBF")
                all_results.append(result)

    if skipped:
        with st.expander("⚠️ Skipped files — click to expand"):
            st.dataframe(pd.DataFrame(skipped))

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
