# Glossary

The dorm speaks German and the code speaks English. This table maps the two. In
user-facing text, use the German term residents use (left column). In code, use the name
on the right.

| German (UI, mails) | Code | Meaning |
| --- | --- | --- |
| Schollheim | – | The dorm. Two houses (Haus 1, Haus 2). |
| Bewohner:in, Mieter:in | `Tenant` (`t_tenant`) | A resident with their own lease. |
| Untermieter:in, Untermiete | `Subtenant` (`t_subtenant`) | Someone living in a tenant's room while the tenant is away. |
| Verwaltung | group `VERWALTUNG`, employeeType `DEPARTMENT` | The two full-time employees. Not tenants. They run leases, money, legal stuff and the parcel desk. |
| HSV (Heimselbstverwaltung) | group `HSV` | The residents' self-government. Everyone holding a Referat or Amt this semester is in the `HSV` LDAP group. |
| Heimrat | group `Heimrat` | The two elected heads of the HSV. They coordinate the Referate and run the semester switch. |
| HSV-Vertretung | group `HSV-Vertreter` | Two residents who represent the HSV on the board of the association that owns the dorm. |
| Referat | `Department` (`t_department`) | An elected responsibility: Barreferat, Netzwerkreferat, Tutoren, … Voted each semester. |
| Amt | `Department` too | Smaller responsibility, e.g. Waschmarkenverkäufer:in, Flursprecher:in. Stored like a Referat. |
| Referent:in | – | Someone holding a Referat. |
| Referatsbewerbung | `EngagementApplication` | Application for a Referat next semester. |
| Engagement / "Amt im Semester X" | `Engagement` (`t_engagement`) | One person holding one Referat in one semester. |
| Punkte, HSV-Punkte | `Engagement.points`, `Tenant.current_points` | Reward for a Referat. Used by the Zimmerreferat and the Verwaltung to decide extensions and room upgrades. |
| Entlastung (Referatsentlastung) | `Engagement.compensate = True` | Confirmation at the end of the semester that the job was done. Only then do the points count. |
| Flur | `Tenant.current_floor`, `Room.floor` | A floor/corridor. Codes: `H1EG`, `H1L1`–`H1L5`, `H1R1`–`H1R5`, `H2EG`, `H2F1`–`H2F5` (house, then section and level; `EG` = ground floor). |
| Flursprecher:in | group `Flursprecher-<Flur>` | Elected floor representative. About one per eight residents. |
| Vollversammlung (VV) | attendance `Event` | Assembly of all residents. Votes on proposals and elects referents. |
| FVV (Flurvertretendenversammlung) | attendance `Event` | Assembly of the Flursprecher:innen. |
| Wohnzeit, Wohnzeitende | `Tenant.move_in` … `Tenant.move_out` | The lease period and its end. |
| Probezeit | `Tenant.probation_end` | The first year of the lease. |
| Wohnzeitverlängerung | `Claim` with `type = EXTENSION` | A resident's request to extend their lease. |
| Verlängerung durch die Verwaltung | `DepartmentExtension` | Months the Verwaltung adds (or removes) by hand. |
| Kündigung | `Termination` | The lease ends early on a fixed date, overriding everything else. |
| Auszug | `Departure` (`t_departure`) | The move-out process. |
| Unterschrift (beim Auszug) | `DepartmentSignature` | A Referat or floor confirming the leaver owes nothing, or entering their debt. |
| Kaution | `Tenant.deposit`, `DepositBank` | Deposit, and the bank account it's paid back to. |
| Umzug | `Rental` (`t_rental`) | Moving to another room inside the dorm. Each room stay is one rental. |
| Paket, Einschreiben | `Parcel` (`t_parcel`) | Mail waiting at the Verwaltung. |
| Semester | `GlobalAppSettings.current_semester` | `SS26` (summer) or `WS26/27` (winter). |
| Anwesenheit | `Event`, `AttendanceSession`, `AttendanceRecord` | QR-code attendance at assemblies and duties. |
| Drucken / Scannen | `Device`, `PrintSession`, `PrintJob`, `Scan` | The dorm printer, billed per page. |
| ADMIN | group `ADMIN` | A single superuser account for the Netzwerkreferat. Passes every access rule. |

## Code-only terms

| Term | Meaning |
| --- | --- |
| employeeType | LDAP attribute: `TENANT`, `DEPARTMENT` (Verwaltung) or `SUBTENANT`. Stored in Django's `user.first_name` because the user model has no field for it. |
| external_id | UUID hex that every legacy row carries. Some URLs use it instead of the integer id. |
| sentinel date `1900-01-01` | `DepartmentSignature.signed_on` value meaning "not signed yet". |
| managed groups | LDAP groups the nightly sync may remove people from. See [../ldap.md](../ldap.md). |
