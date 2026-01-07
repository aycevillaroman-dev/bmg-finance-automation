"""
Automatic Book Segregation Module

Logic:
- If Account is RCBC / Westpac AND Credit > 0 → Cash Disbursement
- If Account is RCBC / Westpac AND Debit > 0 → Cash Receipts
- Else → General Journal
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys
from io import BytesIO

sys.path.append(str(Path(__file__).parent.parent))

from utils import load_logo
from config import AppConfig


# =============================================================================================
# CLASSIFIER
# =============================================================================================

class BookCategoryClassifier:

    TARGET_ACCOUNTS = {
        "RCBC - BMGO(PHP)",
        "RCBC - BMGO(USD)",
        "Westpac - BMG Outsourcing",
    }

    def segregate(self, df: pd.DataFrame) -> dict:
        """
        Segregate dataframe into Cash Disbursement, Cash Receipts, and General Journal.
        """

        df = df.copy()

        # --- Normalize column names ---
        cols = {c.lower().strip(): c for c in df.columns}

        account_col = next((cols[c] for c in ["account", "account title"] if c in cols), None)
        debit_col = next((cols[c] for c in ["debit", "dr"] if c in cols), None)
        credit_col = next((cols[c] for c in ["credit", "cr"] if c in cols), None)

        if not all([account_col, debit_col, credit_col]):
            raise ValueError("Missing required columns: Account, Debit, Credit")

        # --- Ensure numeric values ---
        df[debit_col] = pd.to_numeric(df[debit_col], errors="coerce").fillna(0)
        df[credit_col] = pd.to_numeric(df[credit_col], errors="coerce").fillna(0)

        # --- Classification function ---
        def classify_row(row):
            account = str(row[account_col]).strip()
            debit = row[debit_col]
            credit = row[credit_col]

            if account in self.TARGET_ACCOUNTS:
                if credit > 0:
                    return "Cash Disbursement"
                if debit > 0:
                    return "Cash Receipts"

            return "General Journal"

        df["Book"] = df.apply(classify_row, axis=1)

        return {
            "Cash Disbursement": df[df["Book"] == "Cash Disbursement"].drop(columns="Book"),
            "Cash Receipts": df[df["Book"] == "Cash Receipts"].drop(columns="Book"),
            "General Journal": df[df["Book"] == "General Journal"].drop(columns="Book"),
        }


# =============================================================================================
# UI
# =============================================================================================

def render_segregation_page():

    # --- Display Logo & App Title ---
    logo_url = load_logo()
    if logo_url:
        st.markdown(
            f"""
            <div class="nav-bar">
                <img src="{logo_url}" height="40">
                <h2>{AppConfig.APP_TITLE}</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader("Automatic Book Segregation")

    # --- Load Data ---
    if "processed_df" in st.session_state and st.session_state.processed_df is not None:
        df = st.session_state.processed_df
        st.success("Using cleaned data (duplicates & reversals removed)")
    elif "df_original" in st.session_state and st.session_state.df_original is not None:
        df = st.session_state.df_original
        st.info("Using original uploaded data")
    else:
        st.error("No data available. Please upload an Excel file first.")
        st.stop()

    classifier = BookCategoryClassifier()

    try:
        segregated = classifier.segregate(df)
    except Exception as e:
        st.error(f"Error during segregation: {str(e)}")
        st.stop()

    # --- Preview Segregated Sheets ---
    for sheet_name, sheet_df in segregated.items():
        st.markdown(f"### {sheet_name} ({len(sheet_df)} rows)")
        st.dataframe(sheet_df, use_container_width=True)

    # --- Download All Sheets in One Excel File ---
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for sheet_name, sheet_df in segregated.items():
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
        writer.save()

    st.download_button(
        label="Download Segregated Excel File",
        data=buffer.getvalue(),
        file_name="Book_Segregation.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
