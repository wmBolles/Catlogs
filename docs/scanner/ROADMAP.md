# CatLogs Scanner — Engineering Brief & Roadmap

## 1. Purpose

This document defines the engineering plan for a local, Linux-first scanner capability in CatLogs. The scanner MUST be designed as a system diagnostics feature that complements, rather than replaces, the existing log viewer and process monitor.

The design in this document is intentionally conservative. It SHALL prioritize correctness, user control, data minimization, and transparent operation over broad detection coverage. The scanner SHALL operate in a manner that is understandable to an end user, auditable by the application, and safe when run on an unprivileged workstation or a local administrator account.

The keywords MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, MAY, and OPTIONAL are to be interpreted as described in RFC 2119 and RFC 8174.

## 2. Product intent

CatLogs is a local system logging and diagnostics tool for Linux. The scanner feature SHALL be a first-class component of that workflow and SHALL fit the existing app model:

- local-first operation
- offline-capable analysis by default
- transparent scanning of files, packages, and system state
- process-aware, low-noise workflows
- user consent before sensitive actions or privilege escalation
- clear reporting with a path to remediation

The scanner feature SHALL NOT be designed as a cloud service, remote agent, or opaque background daemon. It SHALL remain a desktop-local utility that works with the live machine and local filesystem.

## 3. Scope

### 3.1 In scope

The scanner capability SHALL include the following planned functional areas:

- file and directory inventory for selected paths
- hash and metadata collection for candidate files
- portable detection rules for suspicious patterns and known bad artifacts
- process-aware inspection using the existing process-monitor data model
- local alerts, threat summary, and risk scoring
- scan history and result persistence in a local database
- safe helper-based privilege escalation for escalated checks
- user-facing controls for scan targets, depth, and scope

### 3.2 Out of scope

The initial scope SHALL exclude the following unless explicitly approved during a later milestone:

- remote fleet scanning
- cloud IoT or distributed endpoint management
- automatic quarantine or destructive remediation
- network packet inspection
- kernel-level exploit mitigation
- continuous server-side analytics or telemetry export

## 4. Design principles

### 4.1 Local-first and user-controlled

The scanner MUST operate on local data only. It MUST NOT automatically transmit filesystem metadata or file samples to a remote service unless the user explicitly enables an opt-in workflow for a later feature. The default operating mode SHALL be offline and privacy-preserving.

### 4.2 Safety by default

The scanner SHALL never execute arbitrary file content as part of the scanning workflow. It MUST read file bytes, metadata, and command-line strings safely. It SHALL use argument vectors and subprocess calls rather than shell-literal execution when the app needs to invoke an external command.

### 4.3 Clear privilege boundaries

The application SHALL separate the GUI process from privileged system inspection. The scanner SHOULD use a helper layer for actions that require elevated privileges. The UI MUST clearly tell the user when a scan is running without privileges, when a helper is in use, and which actions are restricted by the current user.

### 4.4 Minimal noise

The scanner MUST prioritize actionable findings. It SHOULD avoid over-reporting normal system files. It SHALL group findings by severity, scope, and confidence and MUST support a concise summary for normal users.

### 4.5 Explainability

Every finding MUST be accompanied by enough context for a user to understand:

- what was scanned
- what rule or condition triggered the result
- why it is significant
- whether it is informational, suspicious, or critical
- how to investigate or mitigate it

## 5. Architecture

### 5.1 High-level layout

The scanner SHALL be implemented as a dedicated subsystem inside the CatLogs desktop app, aligned with the existing structure in the repository:

- GUI shell in catlogs/gui.py
- data parsing and model logic in catlogs/models.py and related modules
- local configuration in catlogs/config.py
- system/process inspection already centered around catlogs/process_monitor.py and subprocess-based collection
- optional database, scan result, and reporting helpers in future scanner modules

The scanner SHOULD be introduced as a modular subsystem rather than ad hoc logic inside the UI. A recommended module split is:

- scanner/config.py
- scanner/rules.py
- scanner/engine.py
- scanner/collector.py
- scanner/reporting.py
- scanner/history.py
- scanner/privilege.py

This split is RECOMMENDED to preserve readability and future maintenance. The implementation MAY be introduced incrementally without forcing a single large refactor.

### 5.2 Data model

The scanner SHALL maintain a local model for:

- scan sessions
- scan targets
- file inventory records
- file hashes and sizes
- detection rule matches
- findings
- severity and confidence
- risk classification
- timestamps and provenance

The default storage SHOULD be SQLite for local persistence. This choice is RECOMMENDED because it aligns with the local-first requirement and keeps the app self-contained without introducing a heavy service dependency.

### 5.3 Sources of evidence

The scanner SHALL gather evidence from the following sources, where available:

- filesystem metadata from /proc, /etc, and the live filesystem
- process metadata from the existing process-monitor data model
- file hashes and sizes for scanned targets
- package-manager metadata for installed or user-managed files
- user-specified directories and files
- optional external rule feeds only when explicitly configured by the user

The scanner MUST treat data from /proc and the live system as advisory and SHALL verify it against file system state before making a high-confidence claim.

### 5.4 Privilege model

The app SHALL support the following operating modes:

- Unprivileged scan: limited to user-visible files and safe metadata collection
- Elevated scan: optional helper-assisted inspection for system directories, service files, or protected artifacts
- Restricted mode: only non-destructive checks are allowed for safety and transparency

The default mode SHALL be unprivileged. The application MUST require explicit confirmation before any action that may require root privileges or interact with system-critical files.

## 6. Required behavior

The scanner MUST satisfy the following requirements:

1. The user SHALL be able to start a scan from the application UI.
2. The user SHALL be able to select scan scope, including a full system pass or a narrowed directory/file set.
3. The UI MUST present a clear summary of what the scan is checking and what is excluded.
4. The scanner MUST avoid shell injection by using explicit argument lists and safe subprocess handling.
5. File scanning MUST remain deterministic, bounded, and inspectable.
6. The app MUST allow cancellation without leaving a stale scan in an inconsistent state.
7. Results MUST be persisted locally and viewable in a history list.
8. Findings MUST include severity, rule name, path, and context.
9. High-risk or destructive actions MUST require a confirmation dialog.
10. The app MUST remain responsive while a scan runs; long-running work SHALL occur off the Tkinter event thread.

## 7. Risk model and guardrails

### 7.1 Security controls

The scanner SHALL follow these controls:

- no untrusted shell execution
- explicit allowlist for paths and commands
- minimum privilege for privileged checks
- bounded scan depth and worker count
- fail-closed behavior for unsupported file types
- no automatic deletion or modification without user confirmation

### 7.2 Privacy and operational safety

The scanner SHALL avoid reading unrelated user data unless the user selects that content explicitly. It SHOULD support a privacy mode that limits the scan to system artifacts and a user-defined target set. The app MUST not silently expand the scan scope beyond the target selected in the UI.

### 7.3 Performance limits

The scanner SHALL be designed to operate efficiently on a typical local Linux workstation. The default worker count SHOULD be conservative, such as a bounded pool derived from available CPU count. The implementation MUST support cancellation, throttling, and incremental reporting to prevent UI lockups or excessive CPU use.

## 8. Milestone plan

### Milestone M0 — Baseline foundation

Status: planned as the first delivery gate.

Objectives:

- define the scanner subsystem boundaries within the existing CatLogs architecture
- create the local scan session model and result schema
- add configuration for default scan settings and security policy
- establish a safe worker queue and cancellation mechanism
- connect the scanner to the GUI in a non-blocking way

Required deliverables:

- scanner module skeleton with session model and target selection
- local SQLite schema for scan history and findings
- configuration defaults for scan scope, worker count, and sensitivity
- UI stub for a Scanner page or panel
- background worker infrastructure using threads or queue-based event processing

Acceptance criteria:

- the user can open a scanner section in the app
- a scan session can be created and canceled
- results can be stored locally without crashing the app
- the process remains responsive while scanning

Exit criteria:

- the implementation SHALL require no destructive operations
- the scanner SHALL remain transparent and readable to the user
- the UI SHALL be able to show scan progress without blocking the main loop

### Milestone M1 — Target discovery and evidence collection

Status: planned as the second delivery gate.

Objectives:

- enumerate local files and directories in user-selected scopes
- collect metadata and basic hashes for scanned targets
- parse process data and correlate system artifacts with active processes
- implement rule evaluation for suspicious patterns and known local indicators

Required deliverables:

- directory traversal utility with path filtering and depth limits
- SHA-256 or equivalent hash collection for candidate files
- process- and file-based correlation for suspicious runtime artifacts
- rule engine that produces structured findings
- initial severity model for informational, suspicious, and critical results

Acceptance criteria:

- the scanner can process a selected directory or system target
- findings are traceable to the evidence path and rule
- results can be listed in a readable table or detail panel
- scanning is cancellable and does not hang the UI

Exit criteria:

- the detection logic SHALL be explainable and auditable
- it SHALL NOT invoke untrusted commands without safe argument handling
- it SHALL operate on files and metadata only unless a user-approved privileged action is selected

### Milestone M2 — Reporting, review, and privileged checks

Status: planned as the final near-term delivery gate.

Objectives:

- add a review workflow for findings and remediation guidance
- support privileged helper checks for protected system directories and service files
- provide archive/history browsing for previous scans
- finish the UI polish and reporting integration with CatLogs

Required deliverables:

- findings dashboard with severity grouping and drill-down details
- local history view of past scan sessions and findings
- privileged helper or escalation path for selected system checks
- user confirmation flow before any privileged or potentially destructive action
- documentation updates for scanner usage and risk notes

Acceptance criteria:

- the user can view a summary of findings with a clear explanation
- high-risk or privileged actions require explicit confirmation
- scanner history remains available across sessions
- the feature is integrated into the application in a manner consistent with CatLogs design

Exit criteria:

- all scan workflows SHALL be local and transparent
- the app SHALL preserve responsiveness under active scanning
- the implementation SHALL remain safe by default even when a user selects broad system targets

## 9. Implementation notes

### 9.1 Recommended development sequence

The implementation SHOULD evolve in the following sequence:

1. define the scan data model and database schema
2. add a scanner page to the existing GUI shell
3. build a safe background worker flow and cancellation plumbing
4. add target selection and filesystem discovery
5. implement the rule engine and list-based reporting
6. integrate privilege-aware helper checks
7. validate with focused tests and human review

### 9.2 Testing strategy

The scanner SHOULD be validated using a lightweight but meaningful test suite, including:

- unit tests for rule matching and severity classification
- tests for path filtering and traversal boundaries
- tests for scan session creation and cancellation
- tests for safe subprocess argument handling
- smoke tests for UI responsiveness during a simulated scan

The testing approach SHOULD favor local, deterministic fixtures over large external corpora. The scanner MUST be treated as a system-integrity aid, not a blanket security product.

### 9.3 Documentation expectations

The project SHALL keep the scanner documentation synchronized with implementation milestones. At minimum, the following MUST remain current:

- user-facing help text in the app
- public documentation in the website content
- local roadmap and engineering notes in docs/scanner
- any elevated-check warnings or confirmation flows shown in the UI

## 10. Success criteria

The scanner feature SHALL be considered successful when all of the following are true:

- it is understandable and usable by a local Linux user
- it fits the CatLogs architecture without destabilizing the app
- it respects the user’s safety and privacy expectations
- it remains responsive and transparent under scanning load
- it supports review, traceability, and local history for findings
- it requires explicit confirmation for actions that change system state or elevate privilege

This feature is a capability addition to CatLogs, not a replacement for a full endpoint security suite. The implementation SHALL stay aligned with the project’s goals: local diagnostics, system transparency, and careful user control.

## 11. Immediate next action

The project SHOULD begin with Milestone M0 and implement the scanner subsystem in a way that keeps the app stable while adding the first local scan session, history model, and non-blocking UI integration. The design outlined above SHALL be used as the governing specification for any subsequent implementation work.
