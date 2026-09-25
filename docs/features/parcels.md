# Parcels (Pakete)

The Verwaltung receives mail for residents and records it in SmartDorm. The resident gets an
email and picks it up during office hours. Code: `views/parcel_views.py`,
`/api/department/parcels/` (rule `IsVerwaltung`).

- **Create** (`create/`): the recipient is found by **room** (the current tenant of that
  room) or by **name + surname**: current tenants first, then current subtenants. An
  ambiguous name returns 400, and the Verwaltung then uses the room. `quantity` is the number
  of parcels, and `registered` marks an Einschreiben. The mail (`tenant-parcel.html`) says "ein
  Paket", "N Pakete" or "ein Einschreiben".
- **List** (`list/?status=pending|pickedup|all`, default `pending`), newest first.
- **Pick up** (`<external_id>/pickup/`) sets `picked_up`. Doing it twice is harmless.

`Parcel` (`t_parcel`, legacy) points to either a `tenant` or a `subtenant`.
