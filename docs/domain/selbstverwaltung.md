# How the dorm runs

The Schollheim is self-governed: the students run and maintain the dorm themselves.
SmartDorm exists to support that, so knowing how it works explains most of the features.
Source: the user, and <https://www.schollheim.net/selbstverwaltung> (checked 2026-09-25).
The numbers of seats and points change over time. The database (`t_department`) is the
source of truth for the current ones.

## The two sides

**The Verwaltung** is two full-time employees. They aren't residents and have no tenant
record. Their single shared account (`VERWALTUNG` group, employeeType `DEPARTMENT`) uses the
Verwaltung area: creating tenants, moves, subtenants, move-outs, extension requests,
terminations, parcels and printer billing.

**The HSV** (Heimselbstverwaltung) is everyone else who does a job for the dorm:

- **Heimrat:** two elected heads, one elected each year. They coordinate the Referate and
  mediate between the residents, the Verwaltung and the association.
- **HSV-Vertretung:** two representatives on the association's board.
- **Referate:** about 25 responsibilities (Bar, Netzwerk, Tutoren, Finanzen, Zimmer, Aufnahme,
  Tafel, Sport, …), each with a few seats.
- **Ämter:** smaller jobs, like one Flursprecher:in per floor and the Waschmarkenverkäufer:innen.

## The semester cycle

1. **Applications.** The Heimrat opens applications (`applications_open`). Residents
   apply for Referate for the *next* semester, with a motivation text and optional photo.
   Showing them to everyone (`show_applications`) is a separate switch.
2. **Election.** Referents are elected at the **Vollversammlung** (all residents) or the
   **FVV** (Flursprecher:innen only). This happens outside SmartDorm.
3. **Assignment.** The Heimrat or Inforeferat enter the results as engagements for the
   new semester.
4. **Semester switch.** The Heimrat switches `current_semester`. People gain the LDAP
   groups of their new Referat (mailing lists, wiki rights) and lose the old ones.
5. **Entlastung.** At the end of the semester each engagement is confirmed as done
   (`compensate`). Only then do its points count toward the resident's total.

## Points

Every Referat is worth a fixed number of points per semester (`Department.points`, e.g.
75 for the Barreferat, 25 for the Sportreferat, 25 for Flursprecher:innen). Residents
collect them over their stay, and they count toward **longer leases and bigger rooms**.
The **Zimmerreferat and the Verwaltung decide** on those benefits by hand. SmartDorm only
keeps the tally, and must not automate the decisions. For orientation, the resident dashboard
shows the dorm's thresholds for extensions: 75, 150, 250, 300 and 350 points, then +50 per
further extension, each due by move-in + sublet months + (n+1) years + 9 months
(`smartdormv2-frontend/src/utils/extensionLogic.ts`). The rule itself is in the association's
statutes (Vereinsstatuten), which are private. Don't copy them into the repo.

## Who uses which part of SmartDorm

| Who | What they do in SmartDorm | Access rule |
| --- | --- | --- |
| Every resident | profile, contract breakdown, own Referate and points, applications, printing, attendance scan, move-out decision | `LoggedIn` |
| Subtenants | only their own dashboard (and the WLAN/wiki account) | `IsSubtenant` + middleware |
| Verwaltung | everything about leases, parcels, printer billing | `IsVerwaltung` |
| Heimrat | applications, semester switch | `IsHeimrat`, `IsSemesterManager` |
| Heimrat, Inforeferat | enter engagements, Entlastung | `IsEngagementManager` |
| Netzwerkreferat | Referate list, manual LDAP roles, logs, semester switches | `IsNetworkAdmin`, `IsSemesterManager` |
| Heimrat, Info-, Zimmer-, Finanzen-, Schlichtungsreferat, HSV-Vertretung | resident overview, statistics, CSV exports | `CanViewResident*` |
| Tutoren, Bar-, Werk-, Innen-, Finanzenreferat, each Flursprecher:in | sign off leavers and enter debts | `CheckedInView` + per-slug group |
| Event admins (groups set per event) | run attendance sessions | `CheckedInView` + `Event.admin_groups` |
| ADMIN (one account, Netzwerkreferat) | everything | passes every group rule |

Details on the rules: [../permissions.md](../permissions.md).
