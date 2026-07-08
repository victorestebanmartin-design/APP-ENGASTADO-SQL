# Technical Report — COJO SW

**Application:** COJO SW — *Crimping Operations, Jobs & Orders Software* (Automated Crimping System)
**Organisation:** MERAK · Knorr-Bremse
**Audience:** IT Department
**Author:** Víctor Esteban Martín
**Date:** July 2026
**Application version:** 3.0 Pro

---

## 1. What is the application?

**COJO SW** is an **internal web application** for end-to-end management of the **cable crimping process** in production. Its name sums up what it does: **C**rimping (automated terminal crimping process), **O**perations (real-time shop floor management), **J**obs (work orders and production batches), **O**rders (full traceability and tracking) and **SW** (software — local web application). It covers the plant's full work cycle:

1. **Loading the cable lists** (cutting Excel files) from the administration panel.
2. **Label generation** for cable elements (die-cut A4 format and Zebra ZPL printer).
3. **Production orders**: registration, states (pending → in voucher → in progress → completed) and planning.
4. **Work vouchers (bonos)**: grouping of orders manufactured together, assigned to **physical trolleys (carros)** (1–6).
5. **Operator guidance at the machine** (Crimping V3 module): the operator signs in by scanning a barcode, the system shows the pending terminals grouped by machine (to minimise tool changes), and each crimp is confirmed with real-time progress tracking.
6. **Consumables preparation**: ferrules/sleeves (guided placement and generation of supplier order TXT files) and hoses (guided stripping instructions).
7. **Visualisation**: real-time dashboard designed for a shop-floor screen (progress per voucher and per trolley).
8. **Traceability**: PDF report per trolley with terminal, operator, and date/time of each crimp.

Users access the system from any PC on the shop floor using a **web browser**; nothing is installed on client workstations.

---

## 2. Architecture and technologies

| Component | Technology |
|---|---|
| Language | Python 3.13 (64-bit) |
| Web framework | Flask 3.1 (Jinja2 templates) |
| Database | SQLite (single file `data/engastado.db`, WAL mode) |
| Data access | SQLAlchemy + repository layer with parameterised SQL |
| Application server | Waitress (WSGI for Windows) |
| Frontend | Standard HTML, CSS and JavaScript (no frameworks, no external CDNs) |
| Excel processing | pandas + openpyxl |
| Label printing | Zebra printer (ZPL language), with configurable simulation mode |

**Internal structure:** the application follows Flask's *application factory* pattern, with routes separated by functional domain (vouchers, orders, trolleys, labels, ferrules, progress, reports, system…) and a **repository layer** that concentrates all database access. This separation simplifies maintenance and a potential future migration to another database engine.

**Key point:** the application **does not depend on any external service**. It does not use SQL Server, does not call internet APIs, and does not need an internet connection to run. All information lives in a single local SQLite file.

---

## 3. Deployment model (production)

The final installation runs **on the local network, with no internet connection**:

- A **server PC** (Windows 10, 64-bit) runs the application, listening on **TCP port 5001** for the whole local network.
- All other shop-floor PCs access it via browser at `http://SERVER-IP:5001`.
- A complete **offline installation package** is provided (`paquete_offline`): the Python 3.13 installer plus all dependencies pre-downloaded (wheels), with an automatic installer (`INSTALAR_OFFLINE.bat`). Nothing is downloaded from the internet.
- Health-check endpoint: `http://SERVER-IP:5001/health` returns `{"status": "ok"}`.

### Server PC requirements

1. Windows 10, 64-bit.
2. Python 3.13.x, 64-bit (included in the offline package).
3. TCP port 5001 open in Windows Firewall (inbound rule). This is the only step requiring administrator rights; the application itself **does not need administrator privileges** to install or run.
4. **Fixed IP address** so the access URL never changes.
5. (Optional) A scheduled task running `run.bat` at logon, for automatic startup.

### Client PC requirements

- Only a modern browser (Edge, Chrome or Firefox) and access to the local network. No installation.

### Peripherals

- (Optional) **Zebra GK420T** label printer connected to the server. If unavailable, the app runs in simulation mode.
- Standard barcode scanners (keyboard emulation) at operator workstations.

---

## 4. How it was built

Development was done in **Visual Studio Code**, supported by **GitHub Copilot** with its different AI models — mainly **Claude Sonnet and Claude Opus (Anthropic)** — as programming assistants. The workflow was iterative: design of each module, AI-assisted code generation and review, and functional validation on the shop floor with the operators.

Tools used:

- **Visual Studio Code** — main editor / IDE.
- **GitHub Copilot** (Claude Sonnet and Claude Opus models) — AI assistance for design, coding, review and documentation.
- **Python + Flask** — backend development.
- **pytest** — automated testing.

Temporary test environments were used during development to validate the application with real users before the final installation; **those environments are not part of the final solution**, which runs exclusively on the plant's local network.

---

## 5. Security

- **No internet exposure:** the application is only reachable from the local network; in production the server has no internet access.
- **PIN-protected administration panel:** the PIN is not stored in plain text but as a SHA-256 hash in a local `.env` file. After **5 failed attempts, an automatic 15-minute lockout** applies. The admin session expires after 8 hours.
- **Unique session key per installation:** Flask's `SECRET_KEY` is randomly generated on each installation (not hard-coded).
- **Parameterised SQL across the whole data layer:** protection against SQL injection.
- **Restricted file uploads:** only `.xlsx`/`.xls`, 50 MB limit, and validated file paths (there are dedicated path-security tests).
- **Protected writes** on machine and terminal management (admin session only).
- **No sensitive personal data:** the database contains production data (orders, vouchers, terminals) and operator identifiers for traceability.

---

## 6. Scalability and performance

- SQLite with **WAL mode** comfortably supports the real plant load (4–10 concurrent users). The workload is read-heavy with short writes (crimp confirmations), the ideal scenario for SQLite.
- Connections are pooled (automatic verification and recycling) with a 30-second timeout on locks.
- The frontend refreshes through lightweight server requests (real-time progress without page reloads).
- **Growth path:** if the number of users or plants grows significantly in the future, the repository layer allows migrating to a client-server engine (PostgreSQL / SQL Server) without rewriting the business logic. The app can also simply be moved to a more powerful server with no changes at all.

---

## 7. Quality and maintenance

- **A suite of 60+ automated tests (pytest)** covering authentication, vouchers, orders, Excel processing, file security and endpoints. Tests use a temporary database, so they can run while the application is live with no risk to real data.
- **Trivial backup:** just copy the `data\engastado.db` file (it can be copied while the app is running). A daily scheduled copy to another network location is recommended.
- **Application logs** in `logs\app.log`.
- **Updates:** with no internet access, an update consists of replacing the application folder with the new version (the database and `.env` are kept; schema migrations apply automatically at startup).
- **Automatic initialisation:** a fresh installation creates the schema and initial master data (trolleys, workstations, machines, colours) on its own.

---

## 8. Summary for IT

| Aspect | Value |
|---|---|
| Name | COJO SW v3.0 Pro |
| Type | Internal web application (intranet) |
| Server | 1 Windows 10 x64 PC with Python 3.13 |
| Clients | Web browser, no installation |
| Port | TCP 5001 (inbound firewall rule) |
| Internet | **Not required** (100 % offline installation and operation) |
| Database | SQLite, single local file |
| Backup | Copy of the `data\engastado.db` file |
| Administrator rights | Only for the firewall rule |
| External services | None |
