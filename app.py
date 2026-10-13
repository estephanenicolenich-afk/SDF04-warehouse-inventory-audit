import streamlit as st
import pandas as pd
import numpy as np
import datetime
import io

# -----------------------------------------------------------------------------
# Configuration & Setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Warehouse Inventory Audit & Discrepancy Manager",
    page_icon="📦",
    layout="wide",
)



# -----------------------------------------------------------------------------
# LOGIN GATE 
# -----------------------------------------------------------------------------

import hmac
import streamlit as st


st.title("📦 Warehouse Inventory Audit & Discrepancy Manager")
st.subheader("Login to continue")


# -----------------------------------------------------------------------------
# LOGIN & ROLE-BASED ACCESS CONTROL
# -----------------------------------------------------------------------------

import hmac
import streamlit as st

# 1. Load and validate credentials from Streamlit Secrets
try:
    auth = st.secrets["auth"]

    clerk_username = auth["clerk_username"]
    clerk_password = auth["clerk_password"]
    manager_username = auth["manager_username"]
    manager_password = auth["manager_password"]

    if not all([
        clerk_username,
        clerk_password,
        manager_username,
        manager_password
    ]):
        raise ValueError("Missing credentials")

except Exception:
    st.error(
        "Login is unavailable. Please ask the administrator "
        "to configure all required credentials in Streamlit Secrets."
    )
    st.stop()


# 2. Initialize the login session
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False


# 3. Display the login form if the user is not authenticated
if not st.session_state["authenticated"]:

    st.title("📦 Warehouse Inventory Audit & Discrepancy Manager")
    st.subheader("Login")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input(
            "Password",
            type="password"
        )
        submitted = st.form_submit_button(
            "Log in",
            use_container_width=True
        )

    if submitted:
        role = None

        if (
            hmac.compare_digest(username, clerk_username)
            and hmac.compare_digest(password, clerk_password)
        ):
            role = "Clerk"

        elif (
            hmac.compare_digest(username, manager_username)
            and hmac.compare_digest(password, manager_password)
        ):
            role = "Manager"

        if role:
            st.session_state["authenticated"] = True
            st.session_state["role"] = role
            st.session_state["username"] = username
            st.rerun()
        else:
            st.error("Invalid username or password.")

    # IMPORTANT: Stop here so the main app cannot appear before login.
    st.stop()


# 4. Validate the logged-in user's role
role = st.session_state.get("role")

if role not in ("Clerk", "Manager"):
    st.session_state.clear()
    st.rerun()


# 5. Show the current user and provide logout
with st.sidebar:
    st.write(f"Logged in as: **{st.session_state['username']}**")
    st.write(f"Role: **{role}**")

    if st.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# -----------------------------------------------------------------------------
# 6. ROLE-BASED MAIN APPLICATION
# -----------------------------------------------------------------------------

if role == "Clerk":

    st.header("📦 Clerk Section")

# -----------------------------------------------------------------------------
# Module 1: Clerk — Stock Audit Upload
# -----------------------------------------------------------------------------
if role == "Clerk":
    st.header("📋 Module 1: Inventory Clerk Audit Submission")
    st.write(
        "Upload physical count sheets from cycle counts "
        "or annual physical inventory verification."
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Upload Completed Stock Audit Sheet (.csv)",
            type=["csv"],
            key="clerk_audit_upload"
        )

    with col2:
        st.info("""
        **Template Columns Required:**
        - `SKU`: Stock Keeping Unit ID
        - `Physical_Count`: Actual quantity counted on floor
        """)

    if uploaded_file is not None:
        try:
            audit_df = pd.read_csv(uploaded_file)

            st.subheader("Uploaded Audit Sheet Preview")
            st.dataframe(audit_df, use_container_width=True)

            required_columns = ["SKU", "Physical_Count"]

            if not all(col in audit_df.columns for col in required_columns):
                st.error(
                    "The CSV file must contain both "
                    "'SKU' and 'Physical_Count' columns."
                )

            elif not hasattr(st.session_state, "system_inventory"):
                st.error("System inventory has not been initialized.")

            elif st.session_state.system_inventory.empty:
                st.error("System inventory is empty. Upload inventory first.")

            else:
                if st.button(
                    "Submit Audit Batch to Manager Review",
                    type="primary",
                    key="submit_clerk_audit"
                ):
                    inventory = st.session_state.system_inventory

                    # Check that the inventory has the required columns.
                    inventory_columns = [
                        "SKU", "System_Qty", "Unit_Cost", "Item_Name"
                    ]

                    if not all(
                        col in inventory.columns
                        for col in inventory_columns
                    ):
                        st.error(
                            "System inventory is missing one or more required "
                            "columns: SKU, System_Qty, Unit_Cost, Item_Name."
                        )

                    elif audit_df["SKU"].duplicated().any():
                        st.error(
                            "The audit sheet contains duplicate SKUs. "
                            "Please correct them before submitting."
                        )

                    elif audit_df["SKU"].isna().any():
                        st.error(
                            "The audit sheet contains blank SKUs. "
                            "Please correct them before submitting."
                        )

                    elif audit_df["Physical_Count"].isna().any():
                        st.error(
                            "Physical_Count contains blank or invalid values."
                        )

                    else:
                        audit_df["Physical_Count"] = pd.to_numeric(
                            audit_df["Physical_Count"],
                            errors="coerce"
                        )

                        if (
                            audit_df["Physical_Count"].isna().any()
                            or (audit_df["Physical_Count"] < 0).any()
                            or (
                                audit_df["Physical_Count"]
                                % 1 != 0
                            ).any()
                        ):
                            st.error(
                                "Physical_Count must contain whole numbers "
                                "that are zero or greater."
                            )

                        else:
                            # Match uploaded counts against system inventory.
                            merged = pd.merge(
                                inventory,
                                audit_df[["SKU", "Physical_Count"]],
                                on="SKU",
                                how="inner",
                                validate="one_to_one"
                            )

                            if merged.empty:
                                st.error(
                                    "No uploaded SKUs matched the system "
                                    "inventory. Check the SKU values."
                                )

                            else:
                                # Warn if uploaded SKUs are absent from inventory.
                                unmatched_skus = audit_df.loc[
                                    ~audit_df["SKU"].isin(inventory["SKU"]),
                                    "SKU"
                                ].tolist()

                                if unmatched_skus:
                                    st.warning(
                                        "These SKUs were not found in system "
                                        f"inventory and were skipped: {unmatched_skus}"
                                    )

                                merged["Variance_Qty"] = (
                                    merged["Physical_Count"]
                                    - merged["System_Qty"]
                                )

                                merged["Variance_Value"] = (
                                    merged["Variance_Qty"]
                                    * merged["Unit_Cost"]
                                )

                                merged["Status"] = np.where(
                                    merged["Variance_Qty"] == 0,
                                    "Matched",
                                    "Pending Approval"
                                )

                                now = datetime.datetime.now()

                                merged["Audit_ID"] = (
                                    f"AUD-{now.strftime('%Y%m%d%H%M%S')}"
                                )

                                merged["Audit_Date"] = now.strftime(
                                    "%Y-%m-%d %H:%M"
                                )

                                merged["Manager_Notes"] = ""

                                records_to_append = merged[[
                                    "Audit_ID",
                                    "Audit_Date",
                                    "SKU",
                                    "Item_Name",
                                    "System_Qty",
                                    "Physical_Count",
                                    "Variance_Qty",
                                    "Variance_Value",
                                    "Status",
                                    "Manager_Notes"
                                ]]

                                # Initialize audit logs if needed.
                                if "audit_logs" not in st.session_state:
                                    st.session_state.audit_logs = (
                                        records_to_append.iloc[0:0].copy()
                                    )

                                st.session_state.audit_logs = pd.concat(
                                    [
                                        st.session_state.audit_logs,
                                        records_to_append
                                    ],
                                    ignore_index=True
                                )

                                st.success(
                                    "Audit sheet successfully processed "
                                    "and submitted for managerial review!"
                                )

                                st.dataframe(
                                    records_to_append,
                                    use_container_width=True
                                )

        except Exception as e:
            st.error(f"Error processing file: {e}")


# -----------------------------------------------------------------------------
# MANAGER SECTION
# Keep your existing Manager module under this condition.
# -----------------------------------------------------------------------------

elif role == "Manager":

    st.header("🛡️ Manager Section")

   # -----------------------------------------------------------------------------
# Module 2: Manager — Discrepancy Review & Write-Off Authorization
# -----------------------------------------------------------------------------
elif sidebar_role == "Manager: Discrepancy Review":
    st.header("⚖️ Module 2: Manager Discrepancy Review & Write-off Panel")
    
    pending_audits = st.session_state.audit_logs[st.session_state.audit_logs["Status"] == "Pending Approval"]

    if pending_audits.empty:
        st.success("🎉 No pending inventory discrepancies requiring authorization.")
    else:
        st.warning(f"⚠️ Found {len(pending_audits)} item discrepancy records pending authorization.")

        for idx, row in pending_audits.iterrows():
            with st.expander(f"Discrepancy ID: {row['Audit_ID']} | SKU: {row['SKU']} - {row['Item_Name']}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("System Stock", int(row["System_Qty"]))
                c2.metric("Physical Count", int(row["Physical_Count"]))
                c3.metric("Variance Qty", int(row["Variance_Qty"]))
                c4.metric("Financial Impact ($)", f"${row['Variance_Value']:,.2f}")

                notes = st.text_input(f"Manager Reason / Adjustment Notes", key=f"note_{idx}", placeholder="e.g., Damaged during transit, miscount resolved.")

                col_acc, col_rej, _ = st.columns([1, 1, 4])

                with col_acc:
                    if st.button("Authorize Write-off / Adjust", key=f"approve_{idx}", type="primary"):
                        # Update audit log status
                        st.session_state.audit_logs.loc[idx, "Status"] = "Approved (Write-Off)"
                        st.session_state.audit_logs.loc[idx, "Manager_Notes"] = notes

                        # Adjust master system inventory
                        sku_match = st.session_state.system_inventory["SKU"] == row["SKU"]
                        st.session_state.system_inventory.loc[sku_match, "System_Qty"] = row["Physical_Count"]

                        st.success(f"Write-off authorized! System inventory updated for {row['SKU']}.")
                        st.rerun()

                with col_rej:
                    if st.button("Reject Audit Entry", key=f"reject_{idx}"):
                        st.session_state.audit_logs.loc[idx, "Status"] = "Rejected"
                        st.session_state.audit_logs.loc[idx, "Manager_Notes"] = notes
                        st.info(f"Discrepancy record rejected for {row['SKU']}.")
                        st.rerun()

# -----------------------------------------------------------------------------
# Mock System Data Initialization
# -----------------------------------------------------------------------------
def get_initial_system_inventory():
    """Generates base system inventory record."""
    data = [
        {"SKU": "SKU-1001", "Item_Name": "Wireless Industrial Barcode Scanner", "Category": "Electronics", "Location": "Aisle 01-A", "System_Qty": 150, "Unit_Cost": 120.00},
        {"SKU": "SKU-1002", "Item_Name": "Heavy Duty Pallet Jack", "Category": "Machinery", "Location": "Zone B-04", "System_Qty": 12, "Unit_Cost": 450.00},
        {"SKU": "SKU-1003", "Item_Name": "Standard Wooden Pallets (48x40)", "Category": "Packaging", "Location": "Yard 02", "System_Qty": 500, "Unit_Cost": 15.00},
        {"SKU": "SKU-1004", "Item_Name": "Cardboard Boxes (Large 18x18x24)", "Category": "Packaging", "Location": "Aisle 03-C", "System_Qty": 1200, "Unit_Cost": 2.50},
        {"SKU": "SKU-1005", "Item_Name": "Thermal Transfer Label Printer", "Category": "Electronics", "Location": "Aisle 01-B", "System_Qty": 25, "Unit_Cost": 310.00},
        {"SKU": "SKU-1006", "Item_Name": "Bubble Wrap Roll (24 in x 500 ft)", "Category": "Packaging", "Location": "Aisle 03-A", "System_Qty": 85, "Unit_Cost": 45.00},
        {"SKU": "SKU-1007", "Item_Name": "Steel Safety Toe Work Boots", "Category": "PPE", "Location": "Zone C-01", "System_Qty": 60, "Unit_Cost": 85.00},
        {"SKU": "SKU-1008", "Item_Name": "Industrial Stretch Wrap Film", "Category": "Packaging", "Location": "Aisle 03-B", "System_Qty": 200, "Unit_Cost": 18.50},
        {"SKU": "SKU-1009", "Item_Name": "Handheld Mobile Terminal", "Category": "Electronics", "Location": "Aisle 01-A", "System_Qty": 40, "Unit_Cost": 550.00},
        {"SKU": "SKU-1010", "Item_Name": "Heavy Duty Steel Shelving Unit", "Category": "Storage", "Location": "Zone B-01", "System_Qty": 30, "Unit_Cost": 210.00},
    ]
    return pd.DataFrame(data)

# Initialize Session State
if "system_inventory" not in st.session_state:
    st.session_state.system_inventory = get_initial_system_inventory()

if "audit_logs" not in st.session_state:
    st.session_state.audit_logs = pd.DataFrame(columns=[
        "Audit_ID", "Audit_Date", "SKU", "Item_Name", "System_Qty", 
        "Physical_Qty", "Variance_Qty", "Variance_Value", "Status", "Manager_Notes"
    ])

# -----------------------------------------------------------------------------
# App Header & Navigation
# -----------------------------------------------------------------------------
st.title("📦 Warehouse Inventory Audit & Discrepancy Manager")
st.caption("SDF04 Project — Stock Audit Processing & Write-Off Authorization Engine")

sidebar_role = st.sidebar.radio("Select Persona Role", ["Clerk: Stock Audit Upload", "Manager: Discrepancy Review", "System Dashboard & Inventory"])
st.sidebar.divider()

# Helper template download generator
def generate_sample_csv():
    df = st.session_state.system_inventory[["SKU", "Item_Name", "Location"]].copy()
    # Add mock physical counts with intentional discrepancies
    df["Physical_Count"] = [142, 12, 485, 1200, 20, 85, 60, 190, 40, 28]
    return df.to_csv(index=False).encode('utf-8')

st.sidebar.download_button(
    label="📥 Download Sample Audit Sheet Template",
    data=generate_sample_csv(),
    file_name="sample_stock_audit.csv",
    mime="text/csv"
)





# -----------------------------------------------------------------------------
# Module 3: System Dashboard & Master Inventory
# -----------------------------------------------------------------------------
elif sidebar_role == "System Dashboard & Inventory":
    st.header("📊 Module 3: Live System Inventory & Audit Logs")

    tab1, tab2 = st.tabs(["Live Master Inventory", "Historical Audit Log & Reconciliation"])

    with tab1:
        st.subheader("Current Master Inventory Database")
        df_inv = st.session_state.system_inventory.copy()
        df_inv["Total_Stock_Value"] = df_inv["System_Qty"] * df_inv["Unit_Cost"]

        m1, m2, m3 = st.columns(3)
        m1.metric("Total SKU Count", len(df_inv))
        m2.metric("Total Physical Units", f"{df_inv['System_Qty'].sum():,}")
        m3.metric("Total Inventory Valuation", f"${df_inv['Total_Stock_Value'].sum():,.2f}")

        st.dataframe(
            df_inv.style.format({"Unit_Cost": "${:,.2f}", "Total_Stock_Value": "${:,.2f}"}),
            use_container_width=True
        )

    with tab2:
        st.subheader("Audit Trail & Authorization Log")
        if st.session_state.audit_logs.empty:
            st.info("No audit history available yet. Upload audit sheets in the Clerk section.")
        else:
            st.dataframe(
                st.session_state.audit_logs.style.format({"Variance_Value": "${:,.2f}"}),
                use_container_width=True
            )
