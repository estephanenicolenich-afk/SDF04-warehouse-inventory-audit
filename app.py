
import io
import hmac
import uuid
import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from supabase import create_client


# ============================================================
# 1. CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Warehouse Inventory Audit & Discrepancy Manager",
    page_icon="📦",
    layout="wide",
)

BUCKET = "audit-files"
BATCH_SIZE = 100

SAMPLE_INVENTORY = [
    {
        "sku": "SKU-1001",
        "item_name": "Wireless Industrial Barcode Scanner",
        "category": "Electronics",
        "location": "Aisle 01-A",
        "system_qty": 150,
        "unit_cost": 120.00,
    },
    {
        "sku": "SKU-1002",
        "item_name": "Heavy Duty Pallet Jack",
        "category": "Machinery",
        "location": "Zone B-04",
        "system_qty": 12,
        "unit_cost": 450.00,
    },
    {
        "sku": "SKU-1003",
        "item_name": "Standard Wooden Pallets (48x40)",
        "category": "Packaging",
        "location": "Yard 02",
        "system_qty": 500,
        "unit_cost": 15.00,
    },
    {
        "sku": "SKU-1004",
        "item_name": "Cardboard Boxes (Large 18x18x24)",
        "category": "Packaging",
        "location": "Aisle 03-C",
        "system_qty": 1200,
        "unit_cost": 2.50,
    },
    {
        "sku": "SKU-1005",
        "item_name": "Thermal Transfer Label Printer",
        "category": "Electronics",
        "location": "Aisle 01-B",
        "system_qty": 25,
        "unit_cost": 310.00,
    },
    {
        "sku": "SKU-1006",
        "item_name": "Bubble Wrap Roll (24 in x 500 ft)",
        "category": "Packaging",
        "location": "Aisle 03-A",
        "system_qty": 85,
        "unit_cost": 45.00,
    },
    {
        "sku": "SKU-1007",
        "item_name": "Steel Safety Toe Work Boots",
        "category": "PPE",
        "location": "Zone C-01",
        "system_qty": 60,
        "unit_cost": 85.00,
    },
    {
        "sku": "SKU-1008",
        "item_name": "Industrial Stretch Wrap Film",
        "category": "Packaging",
        "location": "Aisle 03-B",
        "system_qty": 200,
        "unit_cost": 18.50,
    },
    {
        "sku": "SKU-1009",
        "item_name": "Handheld Mobile Terminal",
        "category": "Electronics",
        "location": "Aisle 01-A",
        "system_qty": 40,
        "unit_cost": 550.00,
    },
    {
        "sku": "SKU-1010",
        "item_name": "Heavy Duty Steel Shelving Unit",
        "category": "Storage",
        "location": "Zone B-01",
        "system_qty": 30,
        "unit_cost": 210.00,
    },
]


# ============================================================
# 2. SUPABASE CONNECTION
# ============================================================

@st.cache_resource
def get_supabase_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


try:
    supabase = get_supabase_client()
except Exception:
    st.error(
        "Cannot connect to Supabase. Check SUPABASE_URL and "
        "SUPABASE_KEY in Streamlit App Settings → Secrets."
    )
    st.stop()


# ============================================================
# 3. DATABASE HELPERS
# ============================================================

def get_inventory():
    response = (
        supabase.table("inventory_items")
        .select("*")
        .order("sku")
        .limit(5000)
        .execute()
    )
    return response.data or []


def get_audits():
    response = (
        supabase.table("audit_records")
        .select("*")
        .order("id", desc=True)
        .limit(5000)
        .execute()
    )
    return response.data or []


def initialize_inventory():
    """Insert demo inventory only if the inventory table is empty."""
    existing = get_inventory()

    if not existing:
        for start in range(0, len(SAMPLE_INVENTORY), BATCH_SIZE):
            supabase.table("inventory_items").insert(
                SAMPLE_INVENTORY[start:start + BATCH_SIZE]
            ).execute()


def upload_csv_to_storage(file_bytes, filename):
    safe_filename = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        filename,
    )

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        f"{timestamp}_{uuid.uuid4().hex}_{safe_filename}"
    )

    supabase.storage.from_(BUCKET).upload(
        path,
        file_bytes,
        file_options={
            "content-type": "text/csv",
            "upsert": "false",
        },
    )

    return path


def insert_in_batches(records):
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        supabase.table("audit_records").insert(batch).execute()


def get_original_file(path):
    return supabase.storage.from_(BUCKET).download(path)


def money(value):
    return f"₱{float(value or 0):,.2f}"


def make_sample_csv(inventory):
    df = pd.DataFrame(inventory)

    if df.empty:
        return pd.DataFrame(
            columns=["SKU", "Physical_Count"]
        ).to_csv(index=False).encode("utf-8")

    template = df[["sku", "item_name", "location"]].copy()
    template.columns = ["SKU", "Item_Name", "Location"]

    # Leave physical counts blank for the clerk to fill in.
    template["Physical_Count"] = ""

    return template.to_csv(index=False).encode("utf-8")


# ============================================================
# 4. LOGIN AND ROLE-BASED ACCESS
# ============================================================

st.title("📦 Warehouse Inventory Audit & Discrepancy Manager")

try:
    auth = st.secrets["auth"]

    clerk_username = str(auth["clerk_username"])
    clerk_password = str(auth["clerk_password"])
    manager_username = str(auth["manager_username"])
    manager_password = str(auth["manager_password"])

    if not all([
        clerk_username,
        clerk_password,
        manager_username,
        manager_password,
    ]):
        raise ValueError("Empty login credentials")

except Exception:
    st.error(
        "Login is not configured. Add clerk_username, "
        "clerk_password, manager_username, and manager_password "
        "under [auth] in Streamlit Secrets."
    )
    st.stop()


if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False


if not st.session_state["authenticated"]:
    st.subheader("Login to continue")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        submitted = st.form_submit_button(
            "Log in",
            use_container_width=True,
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

    st.stop()


role = st.session_state.get("role")

if role not in ("Clerk", "Manager"):
    st.session_state.clear()
    st.rerun()


with st.sidebar:
    st.write(f"**User:** {st.session_state['username']}")
    st.write(f"**Role:** {role}")

    if st.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# ============================================================
# 5. INITIALIZE DEMO INVENTORY IN SUPABASE
# ============================================================

try:
    initialize_inventory()
except Exception as exc:
    st.error(
        "Could not initialize the inventory database. "
        "Check the inventory_items table and Supabase credentials."
    )
    st.exception(exc)
    st.stop()


# Load the current database records.
try:
    inventory_records = get_inventory()
    audit_records = get_audits()

    inventory_df = pd.DataFrame(inventory_records)
    audit_df = pd.DataFrame(audit_records)

except Exception as exc:
    st.error("Unable to retrieve records from Supabase.")
    st.exception(exc)
    st.stop()


# ============================================================
# 6. CLERK SECTION — UPLOAD STOCK AUDIT
# ============================================================

if role == "Clerk":

    st.header("Module 1: Clerk — Stock Audit Upload")

    st.write(
        "Upload the completed physical stock count. "
        "The system compares your counts with the master inventory."
    )

    st.download_button(
        "Download Sample Audit Sheet Template",
        data=make_sample_csv(inventory_records),
        file_name="sample_stock_audit.csv",
        mime="text/csv",
    )

    uploaded_file = st.file_uploader(
        "Upload Completed Stock Audit Sheet",
        type=["csv"],
        key="clerk_audit_upload",
    )

    if uploaded_file is not None:
        try:
            file_bytes = uploaded_file.getvalue()
            audit_upload_df = pd.read_csv(
                io.BytesIO(file_bytes),
                dtype={"SKU": "string"},
            )

            audit_upload_df.columns = (
                audit_upload_df.columns.str.strip()
            )

            st.subheader("Uploaded Audit Sheet Preview")
            st.dataframe(
                audit_upload_df,
                use_container_width=True,
                hide_index=True,
            )

            required = ["SKU", "Physical_Count"]
            missing = [
                column for column in required
                if column not in audit_upload_df.columns
            ]

            if missing:
                st.error(
                    "Missing required columns: "
                    + ", ".join(missing)
                )

            elif audit_upload_df.empty:
                st.error("The uploaded CSV has no records.")

            else:
                audit_upload_df["SKU"] = (
                    audit_upload_df["SKU"].str.strip()
                )

                if audit_upload_df["SKU"].isna().any() or (
                    audit_upload_df["SKU"] == ""
                ).any():
                    st.error("Every row must have a SKU.")

                elif audit_upload_df["SKU"].duplicated().any():
                    st.error(
                        "Duplicate SKUs found. Each SKU must appear "
                        "only once in an audit batch."
                    )

                else:
                    audit_upload_df["Physical_Count"] = pd.to_numeric(
                        audit_upload_df["Physical_Count"],
                        errors="coerce",
                    )

                    physical_counts = audit_upload_df["Physical_Count"]

                    if (
                        physical_counts.isna().any()
                        or (physical_counts < 0).any()
                        or (physical_counts % 1 != 0).any()
                    ):
                        st.error(
                            "Physical_Count must contain whole numbers "
                            "greater than or equal to zero."
                        )

                    else:
                        inventory_lookup = {
                            item["sku"]: item
                            for item in inventory_records
                        }

                        unmatched = [
                            sku for sku in audit_upload_df["SKU"]
                            if sku not in inventory_lookup
                        ]

                        if unmatched:
                            st.warning(
                                "These SKUs are not in the master "
                                "inventory and will be skipped: "
                                + ", ".join(unmatched)
                            )

                        matched_rows = audit_upload_df[
                            audit_upload_df["SKU"].isin(
                                inventory_lookup.keys()
                            )
                        ]

                        if matched_rows.empty:
                            st.error(
                                "No uploaded SKUs match the master inventory."
                            )

                        elif st.button(
                            "Submit Audit Batch to Manager Review",
                            type="primary",
                            use_container_width=True,
                        ):
                            try:
                                now = datetime.now(timezone.utc)
                                audit_id = (
                                    "AUD-"
                                    + now.strftime("%Y%m%d%H%M%S")
                                    + "-"
                                    + uuid.uuid4().hex[:8].upper()
                                )

                                # Save the original CSV in private storage.
                                file_path = upload_csv_to_storage(
                                    file_bytes,
                                    uploaded_file.name,
                                )

                                records_to_insert = []

                                for _, row in matched_rows.iterrows():
                                    sku = row["SKU"]
                                    item = inventory_lookup[sku]

                                    system_qty = float(
                                        item["system_qty"]
                                    )
                                    physical_qty = float(
                                        row["Physical_Count"]
                                    )
                                    unit_cost = float(
                                        item.get("unit_cost") or 0
                                    )

                                    variance = (
                                        physical_qty - system_qty
                                    )
                                    variance_value = variance * unit_cost

                                    status = (
                                        "Matched"
                                        if variance == 0
                                        else "Pending Approval"
                                    )

                                    clerk_note = ""
                                    if (
                                        "Notes" in audit_upload_df.columns
                                        and pd.notna(
                                            row.get("Notes")
                                        )
                                    ):
                                        clerk_note = str(row["Notes"])

                                    records_to_insert.append({
                                        "audit_id": audit_id,
                                        "audit_date": now.isoformat(),
                                        "sku": sku,
                                        "item_name": item["item_name"],
                                        "category": item.get("category", ""),
                                        "location": item.get("location", ""),
                                        "system_qty": system_qty,
                                        "physical_count": physical_qty,
                                        "variance_qty": variance,
                                        "unit_cost": unit_cost,
                                        "total_value": system_qty * unit_cost,
                                        "variance_value": variance_value,
                                        "clerk_notes": clerk_note,
                                        "manager_notes": "",
                                        "status": status,
                                        "uploaded_by": st.session_state["username"],
                                        "source_file_path": file_path,
                                    })

                                insert_in_batches(records_to_insert)

                                st.success(
                                    f"Audit batch {audit_id} saved! "
                                    f"{len(records_to_insert)} inventory "
                                    "records submitted."
                                )

                                st.dataframe(
                                    pd.DataFrame(records_to_insert),
                                    use_container_width=True,
                                    hide_index=True,
                                )

                                st.rerun()

                            except Exception as exc:
                                st.error(
                                    "Unable to save the audit batch. "
                                    "Check the database and storage setup."
                                )
                                st.exception(exc)

        except Exception as exc:
            st.error("Unable to process the uploaded CSV.")
            st.exception(exc)


    # --------------------------------------------------------
    # Previously uploaded files in Supabase Storage
    # --------------------------------------------------------

    st.divider()
    st.subheader("Previously Uploaded Audit Files")

    try:
        storage_files = (
            supabase.storage.from_(BUCKET).list()
        )

        csv_files = [
            item["name"]
            for item in storage_files
            if item.get("name", "").lower().endswith(".csv")
        ]

        if not csv_files:
            st.info("No CSV files found in the storage bucket.")

        else:
            selected_file = st.selectbox(
                "Choose an existing CSV",
                sorted(csv_files),
            )

            if st.button("Load Existing CSV"):
                file_bytes = get_original_file(selected_file)

                existing_df = pd.read_csv(
                    io.BytesIO(file_bytes)
                )

                st.dataframe(
                    existing_df,
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "Download Original CSV",
                    data=file_bytes,
                    file_name=selected_file,
                    mime="text/csv",
                    key="download_existing_csv",
                )

    except Exception as exc:
        st.error("Could not retrieve files from Supabase Storage.")
        st.exception(exc)


# ============================================================
# 7. MANAGER SECTION
# ============================================================

elif role == "Manager":

    st.header("Manager Section")

    dashboard_tab, review_tab, history_tab = st.tabs([
        "Live Master Inventory",
        "Discrepancy Review",
        "Historical Audit Log",
    ])

    # --------------------------------------------------------
    # Module 3: Live inventory dashboard
    # --------------------------------------------------------

    with dashboard_tab:
        st.subheader("Current Master Inventory")

        current_inventory = get_inventory()
        current_inventory_df = pd.DataFrame(current_inventory)

        if current_inventory_df.empty:
            st.info("No inventory items found.")

        else:
            current_inventory_df["total_stock_value"] = (
                current_inventory_df["system_qty"]
                * current_inventory_df["unit_cost"]
            )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Total SKU Count",
                len(current_inventory_df),
            )

            c2.metric(
                "Total System Units",
                f"{current_inventory_df['system_qty'].sum():,.0f}",
            )

            c3.metric(
                "Total Inventory Value",
                money(
                    current_inventory_df["total_stock_value"].sum()
                ),
            )

            st.dataframe(
                current_inventory_df,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "Export Master Inventory CSV",
                data=current_inventory_df.to_csv(
                    index=False
                ).encode("utf-8"),
                file_name="master_inventory.csv",
                mime="text/csv",
            )


    # --------------------------------------------------------
    # Module 2: Discrepancy review and authorization
    # --------------------------------------------------------

    with review_tab:
        st.subheader(
            "Discrepancy Review & Write-Off Authorization"
        )

        all_audits = get_audits()
        current_audits_df = pd.DataFrame(all_audits)

        if current_audits_df.empty:
            st.info("No audit records are available yet.")

        else:
            pending_df = current_audits_df[
                current_audits_df["status"] == "Pending Approval"
            ]

            st.metric(
                "Pending Discrepancies",
                len(pending_df),
            )

            if pending_df.empty:
                st.success(
                    "No pending inventory discrepancies require authorization."
                )

            else:
                labels = {}

                for record in pending_df.to_dict("records"):
                    label = (
                        f"{record['audit_id']} | "
                        f"{record['sku']} | "
                        f"{record.get('item_name', '')}"
                    )
                    labels[label] = record

                selected_label = st.selectbox(
                    "Select a discrepancy to review",
                    list(labels.keys()),
                )

                record = labels[selected_label]

                st.write(f"**Audit ID:** {record['audit_id']}")
                st.write(f"**SKU:** {record['sku']}")
                st.write(f"**Item:** {record.get('item_name', '')}")

                c1, c2, c3, c4 = st.columns(4)

                c1.metric(
                    "System Stock",
                    f"{float(record['system_qty']):,.0f}",
                )

                c2.metric(
                    "Physical Count",
                    f"{float(record['physical_count']):,.0f}",
                )

                c3.metric(
                    "Variance",
                    f"{float(record['variance_qty']):+,.0f}",
                )

                c4.metric(
                    "Variance Value",
                    money(record.get("variance_value")),
                )

                source_path = record.get("source_file_path")

                if source_path and st.button(
                    "Retrieve Original Audit CSV"
                ):
                    try:
                        original_bytes = get_original_file(source_path)

                        st.download_button(
                            "Download Original Audit File",
                            data=original_bytes,
                            file_name=source_path.split("/")[-1],
                            mime="text/csv",
                            key=f"download_{record['id']}",
                        )

                    except Exception as exc:
                        st.error("Could not retrieve the original CSV.")
                        st.exception(exc)

                with st.form(
                    f"manager_review_{record['id']}"
                ):
                    decision = st.radio(
                        "Manager Decision",
                        ["Approve Write-Off / Adjust", "Reject"],
                    )

                    manager_notes = st.text_area(
                        "Manager Reason / Adjustment Notes",
                        placeholder=(
                            "Explain the decision, discrepancy, "
                            "or adjustment."
                        ),
                    )

                    confirm = st.checkbox(
                        "I confirm this decision is intentional."
                    )

                    submitted = st.form_submit_button(
                        "Save Manager Decision",
                        type="primary",
                    )

                if submitted:
                    if not confirm:
                        st.warning(
                            "Please confirm your decision before saving."
                        )

                    elif not manager_notes.strip():
                        st.warning(
                            "Enter a reason for the manager's decision."
                        )

                    else:
                        try:
                            if decision == "Approve Write-Off / Adjust":
                                new_status = "Approved (Write-Off)"
                            else:
                                new_status = "Rejected"

                            # Save the manager decision in Supabase.
                            (
                                supabase.table("audit_records")
                                .update({
                                    "status": new_status,
                                    "manager_notes": manager_notes.strip(),
                                })
                                .eq("id", record["id"])
                                .execute()
                            )

                            # Only an approved adjustment updates stock.
                            if decision == "Approve Write-Off / Adjust":
                                (
                                    supabase.table("inventory_items")
                                    .update({
                                        "system_qty": record["physical_count"],
                                        "updated_at": datetime.now(
                                            timezone.utc
                                        ).isoformat(),
                                    })
                                    .eq("sku", record["sku"])
                                    .execute()
                                )

                            st.success(
                                f"Decision saved for {record['sku']}."
                            )

                            st.rerun()

                        except Exception as exc:
                            st.error(
                                "Could not save the manager decision."
                            )
                            st.exception(exc)


    # --------------------------------------------------------
    # Historical audit log
    # --------------------------------------------------------

    with history_tab:
        st.subheader("Historical Audit Log & Reconciliation")

        historical_records = get_audits()
        historical_df = pd.DataFrame(historical_records)

        if historical_df.empty:
            st.info(
                "No audit history is available. "
                "Clerks can submit audit sheets from their section."
            )

        else:
            st.dataframe(
                historical_df,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "Export Historical Audit Log CSV",
                data=historical_df.to_csv(
                    index=False
                ).encode("utf-8"),
                file_name="historical_audit_log.csv",
                mime="text/csv",
            )


# ============================================================
# 8. FOOTER
# ============================================================

st.divider()

st.caption(
    "SDF04 Project — Warehouse Inventory Audit & "
    "Discrepancy Manager | Data stored in Supabase"
)
