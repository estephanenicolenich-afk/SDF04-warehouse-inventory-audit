
import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# ---------------- CONFIGURATION ----------------
st.set_page_config(
    page_title="Warehouse Inventory Manager",
    page_icon="📦",
    layout="wide"
)

DB_PATH = "inventory.db"

# Demo credentials. Change these before sharing the app.
auth = st.secrets.get("auth", {})
CLERK_USER = auth.get("clerk_username", "clerk")
CLERK_PASS = auth.get("clerk_password", "clerk123")
MANAGER_USER = auth.get("manager_username", "manager")
MANAGER_PASS = auth.get("manager_password", "manager123")


# ---------------- DATABASE ----------------
def connect_db():
    return sqlite3.connect(DB_PATH, timeout=30)


def initialize_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                sku TEXT PRIMARY KEY,
                item_name TEXT NOT NULL,
                category TEXT DEFAULT '',
                location TEXT DEFAULT '',
                system_count REAL NOT NULL DEFAULT 0,
                unit_cost REAL NOT NULL DEFAULT 0,
                updated_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                item_name TEXT,
                category TEXT,
                location TEXT,
                system_count REAL DEFAULT 0,
                physical_count REAL DEFAULT 0,
                variance REAL DEFAULT 0,
                unit_cost REAL DEFAULT 0,
                total_value REAL DEFAULT 0,
                variance_value REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                manager_notes TEXT DEFAULT '',
                status TEXT DEFAULT 'Pending Approval',
                uploaded_by TEXT,
                source_file TEXT,
                audit_date TEXT
            )
        """)

        # Add starter inventory only when the inventory is empty.
        count = conn.execute(
            "SELECT COUNT(*) FROM inventory"
        ).fetchone()[0]

        if count == 0:
            samples = [
                ("SKU-1001", "USB", "Electronics", "Shelf A1", 120, 941),
                ("SKU-1002", "Keyboard", "Electronics", "Shelf A2", 50, 650),
                ("SKU-1003", "Mouse", "Electronics", "Shelf A3", 80, 350),
                ("SKU-1004", "Monitor", "Electronics", "Shelf B1", 25, 5200),
                ("SKU-1005", "HDMI Cable", "Accessories", "Shelf B2", 100, 180),
                ("SKU-1006", "Webcam", "Electronics", "Shelf B3", 30, 1250),
                ("SKU-1007", "Headset", "Accessories", "Shelf C1", 40, 850),
                ("SKU-1008", "Laptop Stand", "Accessories", "Shelf C2", 20, 700),
                ("SKU-1009", "Ethernet Cable", "Networking", "Shelf C3", 90, 120),
                ("SKU-1010", "Flash Drive", "Storage", "Shelf D1", 60, 300),
            ]

            now = datetime.now().isoformat(timespec="seconds")
            conn.executemany("""
                INSERT INTO inventory
                (sku, item_name, category, location, system_count,
                 unit_cost, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [(*item, now) for item in samples])


def get_inventory():
    with connect_db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM inventory ORDER BY sku", conn
        )


def get_audits(status=None):
    with connect_db() as conn:
        if status and status != "All":
            return pd.read_sql_query(
                "SELECT * FROM audits WHERE status = ? ORDER BY id DESC",
                conn,
                params=(status,)
            )
        return pd.read_sql_query(
            "SELECT * FROM audits ORDER BY id DESC", conn
        )


def money(value):
    return f"₱{float(value):,.2f}"


initialize_db()


# ---------------- LOGIN ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "role" not in st.session_state:
    st.session_state.role = ""

if not st.session_state.logged_in:
    st.title("📦 Warehouse Inventory Audit & Discrepancy Manager")
    st.subheader("Login")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True)

    if submitted:
        if username == CLERK_USER and password == CLERK_PASS:
            st.session_state.logged_in = True
            st.session_state.role = "Clerk"
            st.session_state.username = username
            st.rerun()
        elif username == MANAGER_USER and password == MANAGER_PASS:
            st.session_state.logged_in = True
            st.session_state.role = "Manager"
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Incorrect username or password.")

    st.caption(
        "Demo login — Clerk: clerk / clerk123 | "
        "Manager: manager / manager123"
    )
    st.stop()


# ---------------- SIDEBAR ----------------
role = st.session_state.role
st.sidebar.title("📦 Warehouse Manager")
st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
st.sidebar.write(f"Role: **{role}**")

if role == "Clerk":
    pages = ["Dashboard", "Upload Audit CSV", "Audit History"]
else:
    pages = [
        "Dashboard",
        "Inventory Management",
        "Discrepancy Review",
        "Audit History"
    ]

page = st.sidebar.radio("Navigation", pages)

if st.sidebar.button("Log out", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.role = ""
    st.session_state.pop("username", None)
    st.rerun()


# ---------------- DASHBOARD ----------------
if page == "Dashboard":
    st.title("Warehouse Inventory Dashboard")

    inventory = get_inventory()
    audits = get_audits()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Inventory Items", len(inventory))
    col2.metric(
        "Total Stock Units",
        f"{inventory['system_count'].sum():,.0f}" if not inventory.empty else "0"
    )
    col3.metric(
        "Inventory Value",
        money((inventory["system_count"] * inventory["unit_cost"]).sum())
        if not inventory.empty else "₱0.00"
    )
    pending = (
        int((audits["status"] == "Pending Approval").sum())
        if not audits.empty else 0
    )
    col4.metric("Pending Audits", pending)

    st.subheader("Current Inventory")
    if inventory.empty:
        st.info("No inventory records found.")
    else:
        display = inventory.rename(columns={
            "sku": "SKU",
            "item_name": "Item Name",
            "category": "Category",
            "location": "Location",
            "system_count": "System Count",
            "unit_cost": "Unit Cost",
            "updated_at": "Last Updated"
        })
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.subheader("Recent Audits")
    if audits.empty:
        st.info("No audit records have been uploaded.")
    else:
        recent = audits.head(10).rename(columns={
            "sku": "SKU",
            "item_name": "Item Name",
            "system_count": "System Count",
            "physical_count": "Physical Count",
            "variance": "Variance",
            "status": "Status",
            "audit_date": "Audit Date"
        })
        columns = [
            c for c in [
                "SKU", "Item Name", "System Count", "Physical Count",
                "Variance", "Status", "Audit Date"
            ] if c in recent.columns
        ]
        st.dataframe(recent[columns], use_container_width=True, hide_index=True)


# ---------------- INVENTORY MANAGEMENT ----------------
elif page == "Inventory Management" and role == "Manager":
    st.title("Inventory Management")

    with st.expander("➕ Add Inventory Item"):
        with st.form("add_inventory"):
            sku = st.text_input("SKU").strip().upper()
            item_name = st.text_input("Item Name")
            category = st.text_input("Category")
            location = st.text_input("Location")
            system_count = st.number_input(
                "System Count", min_value=0.0, step=1.0
            )
            unit_cost = st.number_input(
                "Unit Cost (₱)", min_value=0.0, step=1.0
            )
            add = st.form_submit_button("Add Item")

        if add:
            if not sku or not item_name.strip():
                st.error("SKU and Item Name are required.")
            else:
                try:
                    with connect_db() as conn:
                        conn.execute("""
                            INSERT INTO inventory
                            (sku, item_name, category, location,
                             system_count, unit_cost, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sku, item_name.strip(), category, location,
                            system_count, unit_cost,
                            datetime.now().isoformat(timespec="seconds")
                        ))
                    st.success("Inventory item added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That SKU already exists. Use a unique SKU.")

    inventory = get_inventory()
    if not inventory.empty:
        inventory["total_value"] = (
            inventory["system_count"] * inventory["unit_cost"]
        )
        st.dataframe(
            inventory.rename(columns={
                "sku": "SKU",
                "item_name": "Item Name",
                "category": "Category",
                "location": "Location",
                "system_count": "System Count",
                "unit_cost": "Unit Cost",
                "total_value": "Total Value",
                "updated_at": "Last Updated"
            }),
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Update Existing Item")
        sku_options = inventory["sku"].tolist()
        selected_sku = st.selectbox("Select SKU", sku_options)
        selected = inventory[inventory["sku"] == selected_sku].iloc[0]

        with st.form("edit_inventory"):
            edit_name = st.text_input(
                "Item Name", value=str(selected["item_name"])
            )
            edit_category = st.text_input(
                "Category", value=str(selected["category"] or "")
            )
            edit_location = st.text_input(
                "Location", value=str(selected["location"] or "")
            )
            edit_count = st.number_input(
                "System Count",
                min_value=0.0,
                value=float(selected["system_count"]),
                step=1.0
            )
            edit_cost = st.number_input(
                "Unit Cost (₱)",
                min_value=0.0,
                value=float(selected["unit_cost"]),
                step=1.0
            )
            save_item = st.form_submit_button("Save Changes")

        if save_item:
            with connect_db() as conn:
                conn.execute("""
                    UPDATE inventory
                    SET item_name=?, category=?, location=?,
                        system_count=?, unit_cost=?, updated_at=?
                    WHERE sku=?
                """, (
                    edit_name, edit_category, edit_location,
                    edit_count, edit_cost,
                    datetime.now().isoformat(timespec="seconds"),
                    selected_sku
                ))
            st.success("Inventory updated.")
            st.rerun()


# ---------------- CLERK CSV UPLOAD ----------------
elif page == "Upload Audit CSV" and role == "Clerk":
    st.title("Upload Physical Stock Audit")

    st.write(
        "Upload a CSV file containing your physical stock count. "
        "Each valid row will be saved as an audit for manager review."
    )

    st.markdown("""
    **Recommended CSV columns:**
    `SKU`, `Item Name`, `Category`, `Location`,
    `System_Count`, `Physical_Count`, `Unit Cost`, `Notes`

    The SKU column is required. If an item already exists in inventory,
    its current system count and unit cost are used when those fields
    are omitted from the CSV.
    """)

    inventory = get_inventory()
    if not inventory.empty:
        template = inventory.rename(columns={
            "sku": "SKU",
            "item_name": "Item Name",
            "category": "Category",
            "location": "Location",
            "system_count": "System_Count",
            "unit_cost": "Unit Cost"
        })
        template["Physical_Count"] = ""
        template["Notes"] = ""
        template = template[[
            "SKU", "Item Name", "Category", "Location",
            "System_Count", "Physical_Count", "Unit Cost", "Notes"
        ]]
        st.download_button(
            "Download CSV Template",
            data=template.to_csv(index=False).encode("utf-8"),
            file_name="inventory_audit_template.csv",
            mime="text/csv"
        )

    uploaded_file = st.file_uploader("Choose audit CSV", type=["csv"])

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

            # Accept common column name variations.
            aliases = {
                "item_code": "sku",
                "product_code": "sku",
                "item": "item_name",
                "name": "item_name",
                "physical_quantity": "physical_count",
                "audited_quantity": "physical_count",
                "audited_count": "physical_count",
                "system_quantity": "system_count",
                "system_qty": "system_count",
                "unit_price": "unit_cost",
                "remarks": "notes"
            }
            df = df.rename(columns={
                old: new for old, new in aliases.items() if old in df.columns
            })

            if "sku" not in df.columns:
                st.error("Your CSV needs a SKU column (or Item_Code).")
            elif "physical_count" not in df.columns:
                st.error(
                    "Your CSV needs Physical_Count, Physical Quantity, "
                    "or Audited_Quantity."
                )
            else:
                st.subheader("Preview")
                st.dataframe(df.head(20), use_container_width=True)

                if st.button("Save Audit Records", type="primary"):
                    current_inventory = get_inventory()
                    inv_map = {
                        str(row["sku"]).strip().upper(): row
                        for _, row in current_inventory.iterrows()
                    }

                    saved = 0
                    skipped = []

                    with connect_db() as conn:
                        for index, row in df.iterrows():
                            sku = str(row.get("sku", "")).strip().upper()

                            if not sku or sku == "NAN":
                                skipped.append(index + 2)
                                continue

                            try:
                                physical = float(row["physical_count"])
                                if pd.isna(physical) or physical < 0:
                                    raise ValueError()
                            except (ValueError, TypeError):
                                skipped.append(index + 2)
                                continue

                            old = inv_map.get(sku)

                            def number(value, fallback=0.0):
                                try:
                                    result = float(value)
                                    return fallback if pd.isna(result) else result
                                except (ValueError, TypeError):
                                    return fallback

                            system = number(
                                row.get("system_count"),
                                float(old["system_count"]) if old is not None else 0.0
                            )
                            cost = number(
                                row.get("unit_cost"),
                                float(old["unit_cost"]) if old is not None else 0.0
                            )
                            item_name = str(
                                row.get("item_name", "")
                            ).strip()
                            if not item_name or item_name == "nan":
                                item_name = (
                                    str(old["item_name"]) if old is not None else sku
                                )

                            category = str(row.get("category", "") or "")
                            location = str(row.get("location", "") or "")
                            notes = str(row.get("notes", "") or "")

                            if category == "nan":
                                category = str(old["category"] or "") if old is not None else ""
                            if location == "nan":
                                location = str(old["location"] or "") if old is not None else ""
                            if notes == "nan":
                                notes = ""

                            variance = physical - system
                            total_value = physical * cost
                            variance_value = variance * cost

                            # Add previously unknown SKUs to inventory.
                            conn.execute("""
                                INSERT OR IGNORE INTO inventory
                                (sku, item_name, category, location,
                                 system_count, unit_cost, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                sku, item_name, category, location,
                                system, cost,
                                datetime.now().isoformat(timespec="seconds")
                            ))

                            conn.execute("""
                                INSERT INTO audits
                                (sku, item_name, category, location,
                                 system_count, physical_count, variance,
                                 unit_cost, total_value, variance_value,
                                 notes, status, uploaded_by, source_file, audit_date)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                        'Pending Approval', ?, ?, ?)
                            """, (
                                sku, item_name, category, location,
                                system, physical, variance, cost,
                                total_value, variance_value, notes,
                                st.session_state.username,
                                uploaded_file.name,
                                datetime.now().isoformat(timespec="seconds")
                            ))
                            saved += 1

                    st.success(f"Saved {saved} audit record(s) for manager review.")
                    if skipped:
                        st.warning(
                            f"Skipped {len(skipped)} invalid row(s). "
                            f"CSV row numbers: {skipped[:20]}"
                        )
                    st.rerun()

        except Exception as e:
            st.error(f"Could not read or process this CSV: {e}")


# ---------------- MANAGER REVIEW ----------------
elif page == "Discrepancy Review" and role == "Manager":
    st.title("Discrepancy Review")

    filter_status = st.selectbox(
        "Filter by Status",
        ["Pending Approval", "Approved", "Rejected", "All"]
    )
    audits = get_audits(filter_status)

    if audits.empty:
        st.info("No audit records found for this status.")
    else:
        view = audits.rename(columns={
            "id": "Audit ID",
            "sku": "SKU",
            "item_name": "Item Name",
            "system_count": "System Count",
            "physical_count": "Physical Count",
            "variance": "Variance",
            "unit_cost": "Unit Cost",
            "total_value": "Physical Stock Value",
            "variance_value": "Variance Value",
            "notes": "Clerk Notes",
            "status": "Status",
            "uploaded_by": "Uploaded By",
            "source_file": "Source File",
            "audit_date": "Audit Date"
        })
        st.dataframe(view, use_container_width=True, hide_index=True)

        st.subheader("Review an Audit")
        audit_id = st.selectbox(
            "Select Audit ID",
            audits["id"].astype(int).tolist()
        )
        audit = audits[audits["id"] == audit_id].iloc[0]

        c1, c2, c3 = st.columns(3)
        c1.metric("System Count", f"{audit['system_count']:,.2f}")
        c2.metric("Physical Count", f"{audit['physical_count']:,.2f}")
        c3.metric("Variance", f"{audit['variance']:+,.2f}")

        st.write(f"**SKU:** {audit['sku']} — {audit['item_name']}")
        st.write(f"**Clerk Notes:** {audit['notes'] or 'None'}")
        st.write(f"**Current Status:** {audit['status']}")
        st.write(f"**Variance Value:** {money(audit['variance_value'])}")

        manager_notes = st.text_area(
            "Manager Notes",
            value=str(audit["manager_notes"] or ""),
            key=f"manager_notes_{audit_id}"
        )

        if audit["status"] == "Pending Approval":
            col1, col2 = st.columns(2)

            with col1:
                if st.button("✅ Approve & Update Stock", use_container_width=True):
                    with connect_db() as conn:
                        conn.execute("""
                            UPDATE inventory
                            SET system_count=?, updated_at=?
                            WHERE sku=?
                        """, (
                            float(audit["physical_count"]),
                            datetime.now().isoformat(timespec="seconds"),
                            audit["sku"]
                        ))
                        conn.execute("""
                            UPDATE audits
                            SET status='Approved', manager_notes=?
                            WHERE id=?
                        """, (manager_notes, int(audit_id)))

                    st.success(
                        "Audit approved. The inventory system count "
                        "has been updated to the physical count."
                    )
                    st.rerun()

            with col2:
                if st.button("❌ Reject Audit", use_container_width=True):
                    with connect_db() as conn:
                        conn.execute("""
                            UPDATE audits
                            SET status='Rejected', manager_notes=?
                            WHERE id=?
                        """, (manager_notes, int(audit_id)))

                    st.warning(
                        "Audit rejected. The inventory system count was not changed."
                    )
                    st.rerun()
        else:
            if st.button("Save Manager Notes"):
                with connect_db() as conn:
                    conn.execute("""
                        UPDATE audits SET manager_notes=? WHERE id=?
                    """, (manager_notes, int(audit_id)))
                st.success("Manager notes saved.")
                st.rerun()


# ---------------- AUDIT HISTORY ----------------
elif page == "Audit History":
    st.title("Audit History")

    status_filter = st.selectbox(
        "Status",
        ["All", "Pending Approval", "Approved", "Rejected"],
        key="history_status"
    )
    audits = get_audits(status_filter)

    if audits.empty:
        st.info("No audit history available.")
    else:
        history = audits.rename(columns={
            "id": "Audit ID",
            "sku": "SKU",
            "item_name": "Item Name",
            "category": "Category",
            "location": "Location",
            "system_count": "System Count",
            "physical_count": "Physical Count",
            "variance": "Variance",
            "unit_cost": "Unit Cost",
            "total_value": "Total Value",
            "variance_value": "Variance Value",
            "notes": "Clerk Notes",
            "manager_notes": "Manager Notes",
            "status": "Status",
            "uploaded_by": "Uploaded By",
            "source_file": "Source File",
            "audit_date": "Audit Date"
        })

        st.dataframe(history, use_container_width=True, hide_index=True)

        st.download_button(
            "Download Audit History CSV",
            data=history.to_csv(index=False).encode("utf-8"),
            file_name="audit_history.csv",
            mime="text/csv"
        )

st.sidebar.caption("Warehouse Inventory Audit System")
