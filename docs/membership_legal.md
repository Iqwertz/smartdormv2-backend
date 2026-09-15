# HSV-Mitgliedschaft — offene rechtliche Punkte und auszufüllende Platzhalter

Dieses Dokument gehört zum Feature "Mitgliedsbeitritt" (Beitrittserklärung, SEPA-Mandat,
Aufnahmeentscheidung, Mitgliederregister). Es sammelt alles, was **noch ausgefüllt oder
entschieden werden muss**, bevor das Feature produktiv Beiträge einzieht.

> **Hinweis:** Dies ist eine technische Zusammenstellung, keine Rechtsberatung. Die mit
> "prüfen" markierten Punkte sollten mit dem Vorstand bzw. einer rechtskundigen Person
> abgestimmt werden.

---

## 1. Blocker — ohne diese Angaben kann kein Lastschrifteinzug erzeugt werden

Alle Werte stehen in `smartdorm/config.py`. Der Code weigert sich bewusst, eine
pain.008-Datei zu erzeugen, solange sie fehlen (`sepa_utils.check_creditor_config`).

| Konstante | Bedeutung | Status |
|---|---|---|
| `HSV_CREDITOR_ID` | Gläubiger-Identifikationsnummer der Bundesbank | ❌ Platzhalter `DE00ZZZ00000000000` |
| `HSV_CREDITOR_IBAN` | IBAN des Vereinskontos, auf das eingezogen wird | ❌ leer |
| `HSV_CREDITOR_BIC` | BIC des Vereinskontos (für `pain.008.001.02` Pflicht) | ❌ leer |
| `HSV_PRIVACY_POLICY_URL` | Öffentliche URL der HSV-Datenschutzerklärung | ❌ leer (Formular zeigt den Link dann nicht an) |
| `HSV_STATUTES_URL` | Öffentliche URL der Satzung | ❌ leer |

Weitere Werte, die stimmen sollten, aber bereits belegt sind:

| Konstante | Aktuell | Prüfen |
|---|---|---|
| `HSV_MEMBERSHIP_FEE_EUR` | `10.00` | Entspricht das der aktuellen Beitragsordnung? |
| `HSV_COLLECTION_DAY` | `1` (Bankarbeitstag des Monats) | Mit dem Finanzenreferat abstimmen |
| `HSV_PRENOTIFICATION_DAYS` | `5` | Siehe Abschnitt 2 |
| `MEMBERSHIP_EMAIL` | `heimrat@schollheim.net` | Wer soll über neue Anträge informiert werden? |
| `MEMBERSHIP_APPROVER_GROUPS` | Zimmerreferat, Finanzenreferat, Heimrat, ADMIN | Siehe Abschnitt 4 |

Außerdem organisatorisch nötig, unabhängig von der Software:

- **Inkassovereinbarung** mit der Bank, die den Einzug von SEPA-Basislastschriften erlaubt.
- Ein Testlauf der erzeugten Datei im Online-Banking, **bevor** der erste echte Einzug läuft.

---

## 2. Vorabankündigung (Pre-Notification) — inhaltlich ergänzt

Die SEPA-Regeln verlangen, dass der Zahlungspflichtige **14 Kalendertage** vor der Belastung
über Betrag und Fälligkeit informiert wird — *es sei denn*, im Mandat/Vertrag ist eine
kürzere Frist vereinbart.

Der ursprüngliche Entwurf des Formulars enthielt dazu **nichts**. Ohne eine solche Klausel
hätte jeder einzelne Monatseinzug 14 Tage vorher angekündigt werden müssen.

Deshalb wurde in `smartdorm/membership_texts.py` (Schlüssel `sepa_prenotification`) ergänzt:

> Der Mitgliedsbeitrag von derzeit 10,00 € wird jeweils zum 1. Bankarbeitstag eines Monats
> eingezogen. Die Vorabankündigung erfolgt spätestens 5 Kalendertage vor Fälligkeit; die
> Frist wird hiermit gegenüber der gesetzlichen Frist von 14 Kalendertagen entsprechend
> verkürzt. Die Ankündigung kann einmalig für alle wiederkehrenden Einzüge erfolgen.

**Zu prüfen / zu entscheiden:**
- [ ] Ist die Formulierung so gewollt, insbesondere die Verkürzung auf 5 Tage?
- [ ] Die Aufnahme-E-Mail (`email/tenant-membership-approval.html`) ist als einmalige
      Vorabankündigung für alle künftigen Einzüge formuliert. Reicht das dem Verein, oder
      soll vor jedem Einzug eine eigene Ankündigung verschickt werden? (Letzteres ist derzeit
      **nicht** implementiert.)
- [ ] Änderungen an Betrag oder Einzugstermin erfordern eine **neue** Vorabankündigung an alle
      Mitglieder. Das ist ein manueller Vorgang und nicht automatisiert.

---

## 3. Minderjährige

Ein Minderjähriger kann weder wirksam beitreten noch ein SEPA-Mandat erteilen, ohne dass die
gesetzlichen Vertreter zustimmen (§§ 107 f. BGB).

Der Entwurf fragte "Bist du mindestens 18 Jahre alt?", knüpfte daran aber keine Folge.
Implementiert ist jetzt: Das Alter wird **serverseitig aus `Tenant.birthday` berechnet**, und
unter 18 wird der Online-Beitritt abgelehnt (Status `INELIGIBLE`) mit dem Hinweis, sich an
Finanzenreferat oder Heimrat zu wenden.

**Zu entscheiden:**
- [ ] Gibt es ein Papierformular mit Unterschriftsfeld für die gesetzlichen Vertreter?
- [ ] Wer trägt eine so zustande gekommene Mitgliedschaft dann im System nach? (Derzeit gibt
      es dafür **keinen** Weg außer direktem DB-Zugriff.)

---

## 4. Vereinsrecht: Wer entscheidet über die Aufnahme?

Aktuell darf **jede** Person aus Zimmerreferat, Finanzenreferat oder Heimrat einen Antrag
allein genehmigen oder ablehnen (`MEMBERSHIP_APPROVER_GROUPS`).

- [ ] **Prüfen:** Sagt die Satzung, dass der *Vorstand* über die Aufnahme entscheidet? Dann
      wäre eine Aufnahme durch das Zimmerreferat formal fehlerhaft. Die Gruppenliste in
      `config.py` ist der einzige Ort, an dem das geändert werden müsste.
- [ ] **Prüfen (Schriftform, § 126 BGB):** Verlangt die Satzung für die Beitrittserklärung
      Schriftform? Ein Webformular erfüllt Schriftform **nicht**. Falls doch gefordert, wäre
      entweder die Satzung anzupassen oder der Online-Beitritt nicht ausreichend.
- [ ] **Entscheiden (Widerrufsrecht):** Ob das 14-tägige Fernabsatz-Widerrufsrecht
      (§ 312g BGB) für die Mitgliedschaft in einem Idealverein gilt, ist umstritten. Günstige
      Absicherung: freiwillig einräumen und im Text erwähnen ("Austritt innerhalb von 14 Tagen
      formlos möglich"). Derzeit **nicht** im Text und **nicht** implementiert.

---

## 5. Datenschutz

### 5.1 Zugriff auf Zahlungsdaten — Text wurde angepasst

Der Entwurf sagte, auf die Zahlungsdaten habe "das Finanzreferat" Zugriff. Tatsächlich können
alle drei aufnehmenden Referate die IBAN aufdecken, weil sie über den Antrag entscheiden.
Text und System dürfen nicht auseinanderlaufen, deshalb nennt der Datenschutzhinweis jetzt
die aufnehmenden Organe mit.

- [ ] **Prüfen:** Soll es dabei bleiben, oder soll die IBAN doch nur dem Finanzenreferat
      sichtbar sein? Dann `MEMBERSHIP_APPROVER_GROUPS` für die Endpunkte
      `reveal_iban_view` / `list_members_view` auf `MEMBERSHIP_FINANCE_GROUPS` umstellen.

### 5.2 Zwei Verantwortliche, ein System

Schollheim e.V. und HSV e.V. sind getrennte juristische Personen, die sich diese Anwendung
und die Bewohnerdaten teilen.

- [ ] Schriftliche Vereinbarung nach **Art. 26 DSGVO** (gemeinsame Verantwortlichkeit) oder
      **Art. 28 DSGVO** (Auftragsverarbeitung) — je nachdem, wer das System betreibt.
- [ ] Eintrag im **Verzeichnis von Verarbeitungstätigkeiten** (Art. 30) beider Vereine.
- [ ] Aufsichtsbehörde für München: **BayLDA**. Das Beschwerderecht gehört in die
      Datenschutzerklärung, auf die das Formular verlinkt.

### 5.3 Einwilligung Amtsliste

Umgesetzt als freiwillige, separat gespeicherte Einwilligung mit Zeitstempel; Voreinstellung
ist "Keine Antwort", und sie blockiert das Absenden nie (kein Kopplungsverbot-Problem).

- [ ] **Offen:** Es gibt noch **keine** Oberfläche, über die ein Mitglied die Einwilligung
      widerruft. Der Text verspricht aber jederzeitigen Widerruf. Sinnvoller nächster Schritt:
      ein Schalter im Nutzerprofil.

### 5.4 Aufbewahrung / Löschung

- Mandat und Einzugsdaten sind **Buchungsbelege**; die Aufbewahrungsfrist nach § 147 AO wurde
  2025 für Buchungsbelege auf **8 Jahre** verkürzt. Die Beitrittserklärung als Vertrag kann
  abweichend länger aufzubewahren sein.
- Für einen Streitfall gilt zusätzlich: Ein Mitglied kann eine Lastschrift **13 Monate** lang
  als unautorisiert zurückrufen. Der Mandatsnachweis muss also mindestens bis 14 Monate nach
  dem letzten Einzug vorliegen.
- [ ] **Mit dem Steuerberater abstimmen** und danach entscheiden. Es ist bewusst **kein**
      automatischer Löschjob implementiert — eine auf einer Vermutung beruhende Löschung wäre
      schlimmer als gar keine.

---

## 6. Was das System bereits sicherstellt

Zur Einordnung, damit die offenen Punkte oben nicht größer wirken als sie sind:

- **Beweisfähigkeit:** Jeder Antrag speichert die exakte Textfassung (`terms_version`),
  Zeitstempel, angemeldetes Benutzerkonto und IP-Adresse und archiviert ein PDF der Erklärung
  in der Datenbank. Alte Fassungen bleiben in `membership_texts.py` erhalten und werden nie
  überschrieben, sodass ein Antrag von 2026 auch 2031 im Originalwortlaut rekonstruierbar ist.
- **Mandatsreferenz:** wird bei der Genehmigung automatisch als `HSV-<Jahr>-<ID>` vergeben,
  ist eindeutig (DB-Constraint), SEPA-zeichenkonform und ≤ 35 Zeichen. Sie wird dem Mitglied
  in der Aufnahme-E-Mail mitgeteilt, also vor dem ersten Einzug.
- **FRST/RCUR:** Erst- und Folgelastschrift werden aus `last_collection_on` abgeleitet und
  beim Erzeugen einer Einzugsdatei fortgeschrieben. Eine IBAN-Änderung setzt die Sequenz
  bewusst auf FRST zurück.
- **IBAN:** verschlüsselt gespeichert (Fernet, Schlüssel in `FIELD_ENCRYPTION_KEYS`), in
  Listen nur maskiert, und jedes Aufdecken wird mit dem handelnden Benutzer protokolliert.
  **Einschränkung, ehrlich benannt:** Das schützt Datenbank-Dumps und Backups, nicht gegen
  einen Angreifer, der die Anwendung selbst kontrolliert — der Schlüssel liegt in derselben
  `.env`.
- **Ende der Mitgliedschaft:** wird beim Abschluss des Auszugs automatisch gesetzt. Zusätzlich
  überspringt der Einzug jedes Mitglied, dessen `move_out` vor dem Fälligkeitsdatum liegt —
  als Sicherheitsnetz, falls je ein anderer Auszugspfad den Haken vergisst.
- **Doppelanträge** sind durch eine partielle Unique-Constraint ausgeschlossen; eine
  Entscheidung ist nur einmal möglich.

---

## 7. Schlüsselverwaltung (Betrieb)

`FIELD_ENCRYPTION_KEYS` in der `.env` ist eine kommaseparierte Liste von Fernet-Schlüsseln.
Der erste verschlüsselt, alle können entschlüsseln.

Neuen Schlüssel erzeugen:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- [ ] Schlüssel in den Passwort-Vault aufnehmen. **Geht der Schlüssel verloren, sind alle
      gespeicherten IBANs unlesbar** und die Mandate müssten neu eingeholt werden.
- [ ] Beim Rotieren: neuen Schlüssel **vorne** anfügen, alten stehen lassen, betroffene
      Datensätze einmal neu speichern, dann den alten entfernen.
