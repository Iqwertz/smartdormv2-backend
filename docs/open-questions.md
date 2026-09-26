# Open questions

Things the code can't answer. Ask the maintainers, then move the answer into the right doc
and tick the item here (with the date) instead of deleting it.

## Domain

- [ ] What does the end of the probation year (`probation_end`) mean in practice? Does
      anything happen at that date (e.g. easier termination), and should SmartDorm show or
      do something then?
- [ ] Floor codes: what exactly do `L`, `R` and `F` stand for in `H1L3`, `H1R2`, `H2F4`? And
      what are houses `0` and `3` in `t_room.house` (the dorm has two houses)?
- [ ] Is the list of Referate that sign off a move-out (`TUTOREN`, `BAR`, `WERK`, `INNEN`,
      `FINANZEN` + floor) still current?
- [ ] Where does the 8-month window for move-out candidates come from? Is it a rule of the
      Verwaltung?
- [ ] What is `university_confirmation` confirming exactly: a semester abroad, an internship,
      any study-related absence?

## Printing

- [ ] Is the printing system live in production, and where is the printer?
- [ ] Does `smartdorm-print-server` already implement the polling agent (with
      `DEVICE_AGENT_TOKEN`), or still the old scan service? This decides how the public scan
      endpoints can be secured.
- [ ] Why was the agent (polling) model chosen over the push model? Record the reason in
      [decisions.md](decisions.md).

## Operations

- [ ] Is the demo environment (branch `demo-mode`) still hosted somewhere, and is it kept in sync?
- [ ] Unused mail templates (`department-info-ex-tenants`, `*-partner-university-confirmation`,
      `tenant-personal-account`): planned features or v1 leftovers?
