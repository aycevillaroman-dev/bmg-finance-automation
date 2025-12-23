"""
Enhanced Segregation Module with Book Category Classification

This module extends the segregation functionality to include automatic
book category classification (Cash Disbursement, Cash Receipts, General Journal)
based on configurable criteria. It seamlessly integrates with the workspace
to process cleaned Excel data.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import re

# Add the parent directory to sys.path to import from utils and constants
sys.path.append(str(Path(__file__).parent.parent))

from utils import load_logo
from constants import CSS_STYLES, UI_LABELS, COLOR_CODES
from config import AppConfig


# =============================================================================================
# BOOK CATEGORY CLASSIFICATION FUNCTIONS
# =============================================================================================

class BookCategoryClassifier:
    """
    Classifier for determining book categories based on configurable criteria.
    Supports Cash Disbursement, Cash Receipts, and General Journal classification.
    """
    
    def __init__(self):
        """Initialize classifier with default criteria."""
        self.criteria = {
            'cash_disbursement': {
                'keywords': ['payment', 'disbursement', 'expense', 'paid', 'cash out', 'withdrawal', 'payable'],
                'column_patterns': ['debit', 'expense', 'payment', 'vendor', 'payable', 'disbursement'],
                'value_patterns': [r'^-\d+', r'payment', r'expense', r'paid'],
                'amount_condition': 'negative_or_debit'
            },
            'cash_receipts': {
                'keywords': ['receipt', 'income', 'revenue', 'received', 'cash in', 'deposit', 'collection', 'receivable'],
                'column_patterns': ['credit', 'income', 'revenue', 'customer', 'receipt', 'receivable', 'collection'],
                'value_patterns': [r'^\d+', r'receipt', r'income', r'revenue', r'received'],
                'amount_condition': 'positive_or_credit'
            }
        }
    
    def update_criteria(self, category: str, criteria_type: str, values: List[str]):
        """
        Update classification criteria for a specific category.
        
        Args:
            category: 'cash_disbursement' or 'cash_receipts'
            criteria_type: Type of criteria to update (keywords, column_patterns, etc.)
            values: List of new values for the criteria
        """
        if category in self.criteria and criteria_type in self.criteria[category]:
            self.criteria[category][criteria_type] = values
    
    def classify_row(self, row: pd.Series, df_columns: List[str]) -> str:
        """
        Classify a single row into a book category.
        
        Args:
            row: DataFrame row to classify
            df_columns: List of all DataFrame column names
            
        Returns:
            Category name: 'Cash Disbursement', 'Cash Receipts', or 'General Journal'
        """
        row_str = ' '.join([str(val).lower() for val in row.values if pd.notna(val)])
        columns_str = ' '.join([str(col).lower() for col in df_columns])
        
        # Score for each category
        disbursement_score = 0
        receipts_score = 0
        
        # Check Cash Disbursement criteria
        for keyword in self.criteria['cash_disbursement']['keywords']:
            if keyword in row_str or keyword in columns_str:
                disbursement_score += 1
        
        # Check column patterns for disbursement
        for pattern in self.criteria['cash_disbursement']['column_patterns']:
            if any(pattern in str(col).lower() for col in df_columns):
                disbursement_score += 0.5
        
        # Check value patterns for disbursement
        for pattern in self.criteria['cash_disbursement']['value_patterns']:
            if any(re.search(pattern, str(val), re.IGNORECASE) for val in row.values if pd.notna(val)):
                disbursement_score += 1
        
        # Check Cash Receipts criteria
        for keyword in self.criteria['cash_receipts']['keywords']:
            if keyword in row_str or keyword in columns_str:
                receipts_score += 1
        
        # Check column patterns for receipts
        for pattern in self.criteria['cash_receipts']['column_patterns']:
            if any(pattern in str(col).lower() for col in df_columns):
                receipts_score += 0.5
        
        # Check value patterns for receipts
        for pattern in self.criteria['cash_receipts']['value_patterns']:
            if any(re.search(pattern, str(val), re.IGNORECASE) for val in row.values if pd.notna(val)):
                receipts_score += 1
        
        # Determine category based on scores
        if disbursement_score > receipts_score and disbursement_score > 0:
            return 'Cash Disbursement'
        elif receipts_score > disbursement_score and receipts_score > 0:
            return 'Cash Receipts'
        else:
            return 'General Journal'
    
    def classify_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Classify all rows in a DataFrame and add a category column.
        
        Args:
            df: DataFrame to classify
            
        Returns:
            DataFrame with added 'Book_Category' column
        """
        df_copy = df.copy()
        df_copy['Book_Category'] = df_copy.apply(
            lambda row: self.classify_row(row, df.columns.tolist()), 
            axis=1
        )
        return df_copy
    
    def segregate_by_category(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Segregate DataFrame into separate DataFrames by book category.
        
        Args:
            df: DataFrame to segregate
            
        Returns:
            Dictionary mapping category names to their respective DataFrames
        """
        df_classified = self.classify_dataframe(df)
        
        segregated = {}
        for category in ['Cash Disbursement', 'Cash Receipts', 'General Journal']:
            category_df = df_classified[df_classified['Book_Category'] == category].copy()
            # Remove the classification column from final output
            if len(category_df) > 0:
                category_df = category_df.drop(columns=['Book_Category'])
                segregated[category] = category_df
        
        return segregated


# =============================================================================================
# NAVIGATION FUNCTIONS
# =============================================================================================

def go_to_workspace():
    """Navigate back to workspace page."""
    st.session_state.current_page = 'workspace'
    st.rerun()


def go_to_home():
    """Navigate back to home page and reset state."""
    st.session_state.current_page = 'home'
    st.session_state.df_original = None
    st.session_state.deletion_queue = set()
    st.session_state.current_matches = []
    st.session_state.uploaded_file = None
    st.session_state.original_filename = None
    st.session_state.search_suggestions = None
    # Clear segregation-specific states
    if 'processed_df' in st.session_state:
        del st.session_state.processed_df
    if 'segregation' in st.session_state:
        del st.session_state.segregation


# =============================================================================================
# UI RENDERING FUNCTIONS
# =============================================================================================

def render_criteria_editor(classifier: BookCategoryClassifier):
    """
    Render the criteria editor UI for customizing classification rules.
    
    Args:
        classifier: BookCategoryClassifier instance to update
    """
    st.markdown('<h4 style="margin-top: 1.5rem;">Customize Classification Criteria</h4>', unsafe_allow_html=True)
    
    with st.expander("Edit Classification Rules", expanded=False):
        criteria_tab1, criteria_tab2 = st.tabs(["Cash Disbursement", "Cash Receipts"])
        
        with criteria_tab1:
            st.write("**Keywords** (comma-separated)")
            cd_keywords = st.text_area(
                "Keywords for Cash Disbursement",
                value=', '.join(classifier.criteria['cash_disbursement']['keywords']),
                key="cd_keywords_input",
                help="Words that indicate cash disbursement transactions",
                label_visibility="collapsed"
            )
            
            st.write("**Column Name Patterns** (comma-separated)")
            cd_columns = st.text_area(
                "Column patterns for Cash Disbursement",
                value=', '.join(classifier.criteria['cash_disbursement']['column_patterns']),
                key="cd_columns_input",
                help="Column name patterns that suggest disbursement data",
                label_visibility="collapsed"
            )
            
            if st.button("Update Cash Disbursement Criteria", use_container_width=True):
                classifier.update_criteria(
                    'cash_disbursement',
                    'keywords',
                    [k.strip() for k in cd_keywords.split(',') if k.strip()]
                )
                classifier.update_criteria(
                    'cash_disbursement',
                    'column_patterns',
                    [k.strip() for k in cd_columns.split(',') if k.strip()]
                )
                st.success("Cash Disbursement criteria updated")
        
        with criteria_tab2:
            st.write("**Keywords** (comma-separated)")
            cr_keywords = st.text_area(
                "Keywords for Cash Receipts",
                value=', '.join(classifier.criteria['cash_receipts']['keywords']),
                key="cr_keywords_input",
                help="Words that indicate cash receipt transactions",
                label_visibility="collapsed"
            )
            
            st.write("**Column Name Patterns** (comma-separated)")
            cr_columns = st.text_area(
                "Column patterns for Cash Receipts",
                value=', '.join(classifier.criteria['cash_receipts']['column_patterns']),
                key="cr_columns_input",
                help="Column name patterns that suggest receipt data",
                label_visibility="collapsed"
            )
            
            if st.button("Update Cash Receipts Criteria", use_container_width=True):
                classifier.update_criteria(
                    'cash_receipts',
                    'keywords',
                    [k.strip() for k in cr_keywords.split(',') if k.strip()]
                )
                classifier.update_criteria(
                    'cash_receipts',
                    'column_patterns',
                    [k.strip() for k in cr_columns.split(',') if k.strip()]
                )
                st.success("Cash Receipts criteria updated")


def render_segregation_page():
    """
    Render the enhanced segregation page with book category classification.
    
    Provides options for:
    1. Traditional column-based segregation
    2. Automatic book category classification
    3. Hybrid approach (both methods)
    
    Automatically uses processed/cleaned data from workspace if available.
    """
    
    # Load logo
    logo_url = load_logo()
    
    # Navigation Bar
    if logo_url:
        st.markdown(f"""
            <div class="nav-bar">
                <div class="nav-left">
                    <div class="logo-container">
                        <img src="{logo_url}" class="logo-image" alt="Logo">
                        <div class="logo-text">
                            <h2 class="nav-title">{AppConfig.APP_TITLE}</h2>
                            <p class="nav-subtitle">Data Segregation & Book Classification</p>
                        </div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div class="nav-bar">
                <div class="nav-left">
                    <h2 class="nav-title">{AppConfig.APP_TITLE}</h2>
                    <p class="nav-subtitle">Data Segregation & Book Classification</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
    

    
    st.markdown('<div class="content-wrapper">', unsafe_allow_html=True)
    
    # Determine which dataframe to use (processed or original)
    working_df = None
    data_source = None
    
    if 'processed_df' in st.session_state and st.session_state.processed_df is not None:
        working_df = st.session_state.processed_df
        data_source = "cleaned"
        st.success("Using cleaned data from workspace (duplicates removed)")
    elif 'df_original' in st.session_state and st.session_state.df_original is not None:
        working_df = st.session_state.df_original
        data_source = "original"
        st.info("Using original uploaded data")
    else:
        st.error("No data available. Please return to home and upload a file.")
        st.stop()
    
    # Initialize session state
    if 'segregation' not in st.session_state:
        st.session_state.segregation = {
            'enabled': False,
            'mode': 'book_category',
            'column': None,
            'values': []
        }
    
    if 'classifier' not in st.session_state:
        st.session_state.classifier = BookCategoryClassifier()
    
    # Main Layout
    column_left, column_center, column_right = st.columns([3, 3, 2])

    # =============================================================================================
    # LEFT COLUMN: SEGREGATION SETTINGS
    # =============================================================================================
    
    with column_left:
        st.markdown('<h3 class="section-header">Segregation Settings</h3>', unsafe_allow_html=True)
        
        # Segregation mode selection
        segregation_mode = st.radio(
            "**Select Segregation Mode:**",
            options=[
                "Book Category (Auto-classify by type)",
                "Column-Based (Manual selection)",
                "Hybrid (Both methods)"
            ],
            key="segregation_mode_radio",
            help="Choose how to segregate your data"
        )
        
        # Map display text to internal mode
        mode_mapping = {
            "Book Category (Auto-classify by type)": "book_category",
            "Column-Based (Manual selection)": "column",
            "Hybrid (Both methods)": "hybrid"
        }
        st.session_state.segregation['mode'] = mode_mapping[segregation_mode]
        st.session_state.segregation['enabled'] = True
        
        st.markdown("---")
        
        # Book Category Settings (for book_category or hybrid mode)
        if st.session_state.segregation['mode'] in ['book_category', 'hybrid']:
            st.markdown('<h4>Book Category Classification</h4>', unsafe_allow_html=True)
            st.info("""
                **Automatic Classification:**
                - **Cash Disbursement**: Payments, expenses, withdrawals
                - **Cash Receipts**: Income, revenue, deposits
                - **General Journal**: Unmatched transactions
            """)
            
            # Criteria editor
            render_criteria_editor(st.session_state.classifier)
        
        # Column-Based Settings (for column or hybrid mode)
        if st.session_state.segregation['mode'] in ['column', 'hybrid']:
            st.markdown('<h4>Column-Based Segregation</h4>', unsafe_allow_html=True)
            
            segregation_column = st.selectbox(
                "Select column to segregate by",
                options=working_df.columns.tolist(),
                index=None if st.session_state.segregation['column'] not in working_df.columns else 
                         working_df.columns.tolist().index(st.session_state.segregation['column']),
                key="segregation_column_select",
                help="Choose additional column for segregation"
            )
            
            if segregation_column:
                st.session_state.segregation['column'] = segregation_column
                
                unique_values = working_df[segregation_column].dropna().unique()
                unique_values = [str(val) for val in unique_values]
                
                selected_values = st.multiselect(
                    "Select values to include",
                    options=sorted(unique_values),
                    default=st.session_state.segregation['values'] if st.session_state.segregation['values'] else [],
                    key="segregation_values_multiselect",
                    help="Optional: Select specific values to include"
                )
                
                st.session_state.segregation['values'] = selected_values

    # =============================================================================================
    # CENTER COLUMN: PREVIEW
    # =============================================================================================
    
    with column_center:
        st.markdown('<h3 class="section-header">Segregated Data Preview</h3>', unsafe_allow_html=True)
        
        # Generate preview based on mode
        segregated_data = {}
        
        if st.session_state.segregation['mode'] == 'book_category':
            # Book category only
            segregated_data = st.session_state.classifier.segregate_by_category(working_df)
        
        elif st.session_state.segregation['mode'] == 'column':
            # Column-based only
            if st.session_state.segregation['column']:
                col = st.session_state.segregation['column']
                vals = st.session_state.segregation['values']
                
                if vals:
                    filtered_df = working_df[working_df[col].isin(vals)]
                else:
                    filtered_df = working_df
                
                for value in filtered_df[col].unique():
                    if str(value) in vals or not vals:
                        segregated_data[str(value)] = filtered_df[filtered_df[col] == value]
        
        elif st.session_state.segregation['mode'] == 'hybrid':
            # First classify by book category
            book_segregated = st.session_state.classifier.segregate_by_category(working_df)
            
            # Then subdivide by column if specified
            if st.session_state.segregation['column']:
                col = st.session_state.segregation['column']
                vals = st.session_state.segregation['values']
                
                for category, category_df in book_segregated.items():
                    if vals:
                        filtered = category_df[category_df[col].isin(vals)]
                    else:
                        filtered = category_df
                    
                    for value in filtered[col].unique():
                        if str(value) in vals or not vals:
                            key = f"{category} - {value}"
                            segregated_data[key] = filtered[filtered[col] == value]
            else:
                segregated_data = book_segregated
        
        # Display preview
        if segregated_data:
            tab_names = list(segregated_data.keys())[:5]
            tabs = st.tabs([f"{name[:20]}{'...' if len(name) > 20 else ''}" for name in tab_names])
            
            for i, (group_name, group_df) in enumerate(segregated_data.items()):
                if i < 5:
                    with tabs[i]:
                        st.write(f"**{group_name}** ({len(group_df)} rows)")
                        st.dataframe(group_df, height=300, use_container_width=True)
            
            if len(segregated_data) > 5:
                st.info(f"Showing first 5 of {len(segregated_data)} total groups.")
            
            # Summary
            total_rows = sum(len(df) for df in segregated_data.values())
            st.markdown(f"""
                <div style='background: #f8fafc; padding: 1rem; border-radius: 8px; margin: 1rem 0;'>
                    <p style='margin: 0.25rem 0; color: #475569;'>
                        <strong>Total Groups:</strong> {len(segregated_data)}
                    </p>
                    <p style='margin: 0.25rem 0; color: #475569;'>
                        <strong>Total Rows:</strong> {total_rows}
                    </p>
                    <p style='margin: 0.25rem 0; color: #475569;'>
                        <strong>Source Data Size:</strong> {len(working_df)} rows
                    </p>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No segregated data to preview. Adjust settings.")
            st.dataframe(working_df, height=400, use_container_width=True)

    # =============================================================================================
    # RIGHT COLUMN: DOWNLOAD
    # =============================================================================================

    with column_right:
        st.markdown('<h3 class="section-header">Download Options</h3>', unsafe_allow_html=True)
        
        if segregated_data:
            st.success(f"Ready to download {len(segregated_data)} file(s)")
            
            download_option = st.radio(
                "Choose format:",
                options=["ZIP Archive", "Individual Files"],
                key="download_option_radio"
            )
            
            if download_option == "Individual Files":
                st.write("**Downloads:**")
                for group_name, group_df in list(segregated_data.items())[:10]:
                    safe_name = re.sub(r'[^\w\s-]', '', group_name).strip()
                    filename = f"{Path(st.session_state.original_filename).stem}_{safe_name}.xlsx"
                    
                    from io import BytesIO
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        group_df.to_excel(writer, index=False, sheet_name='Sheet1')
                    
                    st.download_button(
                        label=f"{safe_name[:25]}",
                        data=output.getvalue(),
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key=f"download_{safe_name}"
                    )
                
                if len(segregated_data) > 10:
                    st.info(f"Showing 10 of {len(segregated_data)}. Use ZIP for all files.")
            
            else:  # ZIP Archive
                import zipfile
                from io import BytesIO
                
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for group_name, group_df in segregated_data.items():
                        safe_name = re.sub(r'[^\w\s-]', '', group_name).strip()
                        filename = f"{Path(st.session_state.original_filename).stem}_{safe_name}.xlsx"
                        
                        excel_buffer = BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            group_df.to_excel(writer, index=False, sheet_name='Sheet1')
                        
                        zip_file.writestr(filename, excel_buffer.getvalue())
                
                st.download_button(
                    label="Download All as ZIP",
                    data=zip_buffer.getvalue(),
                    file_name=f"{Path(st.session_state.original_filename).stem}_segregated.zip",
                    mime="application/zip",
                    use_container_width=True
                )
        else:
            st.info("Configure settings to enable downloads.")
    
    st.markdown('</div>', unsafe_allow_html=True)