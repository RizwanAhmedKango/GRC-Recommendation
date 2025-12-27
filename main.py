import streamlit as st
import pandas as pd

# --- 1. Robust Parser (same as before) ---
def parse_pivot_rules(file_path: str, sheet_name: str = "Sheet1") -> pd.DataFrame:
    df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

    # Find the header row
    header_row_idx = None
    for i, row in df_raw.iterrows():
        if "Segment" in row.values and "Supplier / Product" in row.values:
            header_row_idx = i
            break

    if header_row_idx is None:
        raise ValueError("Header row not found in the Excel sheet.")

    df = df_raw.iloc[header_row_idx + 1:].copy()
    df.columns = df_raw.iloc[header_row_idx].tolist()
    df.columns = df.columns.str.strip()

    # Define columns
    key_cols = [
        "Segment",
        "Modules(tags)",
        "Hosting",
        "Orientation",
        "Regulatory focus (typical)",
        "AU support", # Keep for display
        "Impl", # Keep for display
        "Proj$", # Keep for display
        "Lic$ (p.a.)" # Keep for display
    ]
    supplier_col = "Supplier / Product"

    # Forward-fill only key columns
    for col in key_cols:
        df[col] = df[col].fillna(method='ffill')

    # Drop rows without supplier
    df = df.dropna(subset=[supplier_col])
    df[supplier_col] = df[supplier_col].astype(str).str.strip()
    df = df[df[supplier_col] != ""]

    # Remove summary rows
    df = df[~df[supplier_col].str.contains("Grand Total", case=False, na=False)]
    df = df[~df["Segment"].str.contains("Grand Total", case=False, na=False)]

    df = df.reset_index(drop=True)
    df = df.drop_duplicates()

    return df

# --- 2. Load Data (on first run) ---
@st.cache_data
def load_data():
    df = parse_pivot_rules("Pivot Table.xlsx")  # Update path if needed
    return df

df = load_data()

# --- 3. Initialize Session State for ALL widget keys (CRITICAL: Must happen before widgets) ---
# This ensures the state variables exist before widgets try to access them.
# Use the exact key names as they appear in the st.* widgets.
widget_keys = ['seg_widget', 'mod_widget', 'host_widget', 'orient_widget', 'reg_widget']

# Initialize each key if it doesn't exist
for key in widget_keys:
    if key not in st.session_state:
        if 'mod' in key: # If the key is for the multi-select widget
            st.session_state[key] = []
        else: # For all other selectbox widgets
            st.session_state[key] = ""

# --- 4. Reset Function (Called by Button) ---
def reset_filters():
    # Reset the session state variables that correspond to the widget keys
    # The keys must match exactly those used in the widgets and initialization
    st.session_state.seg_widget = ""
    st.session_state.mod_widget = [] # Reset multi-select to empty list
    st.session_state.host_widget = ""
    st.session_state.orient_widget = ""
    st.session_state.reg_widget = ""

# --- 5. Streamlit App Layout ---
st.title("🔍 GRC Supplier Finder (Strategic Filters)")

st.markdown("""
Select strategic criteria below. The table updates automatically to show matching suppliers
and their implementation details (AU Support, Timeline, Budgets).
*Note: You can select multiple modules.*
""")

# --- 6. Filter Panel (Sidebar - Strategic Criteria Only) ---
with st.sidebar:
    st.header("Strategic Filters")
    
    # Define options for strategic filters only
    seg_opts = [""] + sorted(df["Segment"].dropna().unique())
    mod_opts = sorted(df["Modules(tags)"].dropna().unique()) # All modules for multi-select
    host_opts = [""] + sorted(df["Hosting"].dropna().unique())
    orient_opts = [""] + sorted(df["Orientation"].dropna().unique())
    reg_opts = [""] + sorted(df["Regulatory focus (typical)"].dropna().unique())

    # Create widgets with explicit keys.
    # These keys must match the ones used in initialization and reset_filters.
    st.selectbox("Segment", options=seg_opts, key='seg_widget')
    st.multiselect("Module(s)", options=mod_opts, key='mod_widget')
    st.selectbox("Hosting", options=host_opts, key='host_widget')
    st.selectbox("Orientation", options=orient_opts, key='orient_widget')
    st.selectbox("Regulatory Focus", options=reg_opts, key='reg_widget')

    # Add Reset Button
    st.button("Reset All Filters", on_click=reset_filters)

# --- 7. Create User Answers Dictionary ---
# Read the values directly from the session_state variables linked to the widgets.
# The keys here must match the widget keys.
user_strategic_answers = {}
if st.session_state.seg_widget: # Read from st.session_state.seg_widget
    user_strategic_answers["Segment"] = st.session_state.seg_widget
if st.session_state.mod_widget: # Read from st.session_state.mod_widget
    user_strategic_answers["Modules(tags)"] = st.session_state.mod_widget
if st.session_state.host_widget: # Read from st.session_state.host_widget
    user_strategic_answers["Hosting"] = st.session_state.host_widget
if st.session_state.orient_widget: # Read from st.session_state.orient_widget
    user_strategic_answers["Orientation"] = st.session_state.orient_widget
if st.session_state.reg_widget: # Read from st.session_state.reg_widget
    user_strategic_answers["Regulatory focus (typical)"] = st.session_state.reg_widget


# --- 8. Display Active Filters in Main Window ---
# Create a list of active filter strings
active_filters = []
for key, value in user_strategic_answers.items():
    if value: # Check if value is not empty
        if key == "Modules(tags)": # Special handling for multi-select list (using session_state key)
            # The key for Modules in user_strategic_answers is still the original column name
            # The value comes from st.session_state.mod_widget
            active_filters.append(f"**{key}**: {', '.join(sorted(st.session_state.mod_widget))}")
        else: # Single-select filters
            # Use the original column name as the display key
            # Get the value from the corresponding session_state variable
            # The session_state variable name is the widget key
            # Derive the session_state key from the original data column name
            # This map is necessary because column names are not valid Python identifiers for keys
            col_to_key_map = {
                "Segment": "seg_widget",
                "Hosting": "host_widget",
                "Orientation": "orient_widget",
                "Regulatory focus (typical)": "reg_widget"
            }
            session_state_key = col_to_key_map[key]
            active_filters.append(f"**{key}**: {st.session_state[session_state_key]}")

if active_filters:
    st.subheader("Active Strategic Filters")
    st.markdown(" &nbsp; | &nbsp; ".join(active_filters)) # Join with a separator
    st.divider() # Add a visual separator

# --- 9. Matching Logic (Strategic Filters Only) ---
# Apply filters: only keep suppliers that match ALL selected strategic criteria
# For Modules, check if the supplier's module is in the user's selected list
current_df = df.copy()

for key, value in user_strategic_answers.items():
    if key == "Modules(tags)":
        # 'value' comes from st.session_state.mod_widget
        # Keep rows where the module is in the selected list (if list is not empty)
        if value: # Ensure the list is not empty
            current_df = current_df[current_df[key].isin(value)]
    else:
        # 'value' comes from the corresponding session_state variable (e.g., st.session_state.seg_widget)
        # Keep rows where the column value matches the selected value (if not empty)
        if value:
            current_df = current_df[current_df[key] == value]

# Get the filtered DataFrame with all details
filtered_df = current_df.copy()

# --- 10. Consolidate Unique Suppliers with Aggregated Details ---
if not filtered_df.empty:
    # Group by Supplier and aggregate other columns
    # Join unique values with a comma and space, removing duplicates
    aggregated_df = filtered_df.groupby("Supplier / Product").agg({
        "AU support": lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
        "Impl": lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
        "Proj$": lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
        "Lic$ (p.a.)": lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
        # Add other detail columns here if needed later
    }).reset_index()

    # Rename columns for better readability if needed
    aggregated_df = aggregated_df.rename(columns={
        "AU support": "AU Support",
        "Impl": "Impl. Time",
        "Proj$": "Proj. Budget",
        "Lic$ (p.a.)": "Lic. Budget (p.a.)"
    })

    # Sort by Supplier name for consistency
    aggregated_df = aggregated_df.sort_values(by="Supplier / Product").reset_index(drop=True)

else:
    # If no matches, create an empty DataFrame with the correct columns
    aggregated_df = pd.DataFrame(columns=["Supplier / Product", "AU Support", "Impl. Time", "Proj. Budget", "Lic. Budget (p.a.)"])


# --- 11. Display Results (Unique Suppliers Table) ---
st.header("Matching Suppliers & Details")

if not user_strategic_answers: # Check if the dictionary is empty
    st.info("Please select at least one strategic criterion to filter the suppliers.")
elif aggregated_df.empty:
    st.warning("❌ No suppliers match your current strategic criteria. Please adjust your filters.")
else:
    st.success(f"Found {len(aggregated_df)} unique supplier(s) matching your criteria. Details below:")

    # Display the aggregated table
    st.dataframe(aggregated_df, use_container_width=True, hide_index=True)

# Optional: Debug - Show current selections
# st.write("### Debug: Current Strategic Selections")
# st.write(user_strategic_answers)
# st.write("### Debug: Session State Keys")
# for k in ['seg_widget', 'mod_widget', 'host_widget', 'orient_widget', 'reg_widget']:
#     st.write(f"{k}: {st.session_state.get(k, 'NOT FOUND')}")