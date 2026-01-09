import streamlit as st
import pandas as pd
from io import BytesIO
import re

# =============================================================================================
# CONFIGURATION & UTILS
# =============================================================================================
try:
    from utils import load_logo
    from config import AppConfig
except ImportError:
    class AppConfig:
        APP_TITLE = "Book Segregation Tool"
    def load_logo(): return None


# =============================================================================================
# CLASSIFIER LOGIC
# =============================================================================================

class BookCategoryClassifier:

    def _get_column_name(self, df: pd.DataFrame, candidates: list) -> str:
        """
        Helper to find a column name from a list of candidates (case-insensitive).
        """
        cols = {c.lower().strip(): c for c in df.columns}
        for cand in candidates:
            if cand.lower() in cols:
                return cols[cand.lower()]
        return None

    def clean_reversals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Removes rows where the Narration or Description indicates a reversal.
        """
        target_cols = [self._get_column_name(df, ["narration"]), 
                       self._get_column_name(df, ["description"])]
        
        target_cols = [c for c in target_cols if c] 

        if not target_cols:
            return df 

        pattern = r"(reversal of|reversed)"
        
        mask = pd.Series(False, index=df.index)
        for col in target_cols:
            mask |= df[col].astype(str).str.contains(pattern, case=False, regex=True, na=False)

        return df[~mask].copy()

    def segregate(self, df: pd.DataFrame) -> dict:
        """
        Segregates data into Cash Disbursement, Cash Receipts, and General Journal.
        
        UPDATED LOGIC (Standard Accounting):
        - Bank Credit = Disbursement (Money Out)
        - Bank Debit  = Receipt (Money In)
        - AP Debit    = Disbursement (Paying Bill)
        - AR Credit   = Receipt (Customer Payment)
        """
        df = df.copy()

        # 1. Clean Reversals
        df = self.clean_reversals(df)

        # 2. Identify Key Columns
        id_col = self._get_column_name(df, ["journal id", "journal no", "id", "transaction id"])
        account_col = self._get_column_name(df, ["account", "account code", "account title"])
        debit_col = self._get_column_name(df, ["debit", "dr"])
        credit_col = self._get_column_name(df, ["credit", "cr"])
        narration_col = self._get_column_name(df, ["narration", "description", "details", "memo"])

        if not all([account_col, debit_col, credit_col]):
            raise ValueError("Missing required columns: Account, Debit, Credit")
        
        if not id_col:
             raise ValueError("Could not find 'Journal ID' column to group transactions.")

        # ==============================================================================
        # STEP A: AGGRESSIVE ID FILLING
        # ==============================================================================
        df[id_col] = df[id_col].astype(str).str.strip()
        
        garbage_patterns = [
            r'^total.*',       # Starts with "Total"
            r'^grand total.*', # Starts with "Grand Total"
            r'^nan$',          
            r'^none$',         
            r'^\s*$'           
        ]
        combined_pattern = '|'.join(garbage_patterns)
        df[id_col] = df[id_col].replace(to_replace=combined_pattern, value=pd.NA, regex=True)
        
        df[id_col] = df[id_col].ffill()
        df = df.dropna(subset=[id_col])
        
        # ==============================================================================

        # 3. Ensure numeric values
        df[debit_col] = pd.to_numeric(df[debit_col], errors="coerce").fillna(0)
        df[credit_col] = pd.to_numeric(df[credit_col], errors="coerce").fillna(0)

        # ==============================================================================
        # STEP B: IDENTIFY CATEGORIES
        # ==============================================================================
        
        acc_text = df[account_col].astype(str).str.lower().str.strip()
        
        narr_text = pd.Series("", index=df.index)
        if narration_col:
             narr_text = df[narration_col].astype(str).str.lower().str.strip()

        # 1. Identify BANK (Check Account AND Narration)
        bank_pattern = r"rcbc|westpac"
        is_bank_acc = acc_text.str.contains(bank_pattern, case=False, regex=True, na=False)
        is_bank_narr = narr_text.str.contains(bank_pattern, case=False, regex=True, na=False)
        is_bank_related = is_bank_acc | is_bank_narr

        # 2. Identify ACCOUNTS PAYABLE (Liability)
        is_ap = acc_text.str.contains(r"accounts payable|trade creditors", case=False, regex=True, na=False)

        # 3. Identify TRADE DEBTORS (Asset)
        is_debtor = acc_text.str.contains(r"trade debtors|accounts receivable", case=False, regex=True, na=False)

        # ==============================================================================
        # STEP C: DEFINE TRIGGERS
        # ==============================================================================

        # --- CASH RECEIPTS (Money In) ---
        # 1. Bank is DEBITED (Asset Increases)
        # 2. Trade Debtors is CREDITED (Asset Decreases - Customer paid)
        df['__is_receipt_trigger'] = (is_bank_related & (df[debit_col] > 0)) | \
                                     (is_debtor & (df[credit_col] > 0))

        # --- CASH DISBURSEMENTS (Money Out) ---
        # 1. Bank is CREDITED (Asset Decreases)
        # 2. Accounts Payable is DEBITED (Liability Decreases - We paid bill)
        df['__is_disburse_trigger'] = (is_bank_related & (df[credit_col] > 0)) | \
                                      (is_ap & (df[debit_col] > 0))

        # ==============================================================================
        # STEP D: GROUP DECISION
        # ==============================================================================
        
        group_is_receipt = df.groupby(id_col)['__is_receipt_trigger'].transform('any')
        group_is_disburse = df.groupby(id_col)['__is_disburse_trigger'].transform('any')

        def assign_book(row_idx):
            if group_is_receipt[row_idx]:
                return "Cash Receipts"
            elif group_is_disburse[row_idx]:
                return "Cash Disbursement"
            else:
                return "General Journal"

        df['Book'] = df.index.to_series().apply(assign_book)
        df = df.drop(columns=['__is_receipt_trigger', '__is_disburse_trigger'])

        return {
            "Cash Disbursement": df[df["Book"] == "Cash Disbursement"].drop(columns="Book"),
            "Cash Receipts": df[df["Book"] == "Cash Receipts"].drop(columns="Book"),
            "General Journal": df[df["Book"] == "General Journal"].drop(columns="Book"),
        }


# =============================================================================================
# UI RENDERER
# =============================================================================================

def render_segregation_page():

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

    if "processed_df" in st.session_state and st.session_state.processed_df is not None:
        df = st.session_state.processed_df
        st.success("Using cleaned data")
    elif "df_original" in st.session_state and st.session_state.df_original is not None:
        df = st.session_state.df_original
        st.info("Using original uploaded data")
    else:
        st.error("No data available. Please upload an Excel file first.")
        st.stop()

    classifier = BookCategoryClassifier()

    try:
        segregated = classifier.segregate(df)
    except ValueError as ve:
        st.error(f"Data Error: {str(ve)}")
        st.stop()
    except Exception as e:
        st.error(f"Unexpected Error: {str(e)}")
        st.stop()

    for sheet_name, sheet_df in segregated.items():
        st.markdown(f"### {sheet_name} ({len(sheet_df)} rows)")
        st.dataframe(sheet_df, use_container_width=True)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for sheet_name, sheet_df in segregated.items():
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
    st.download_button(
        label="Download Segregated Excel File",
        data=buffer.getvalue(),
        file_name="Book_Segregation.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )