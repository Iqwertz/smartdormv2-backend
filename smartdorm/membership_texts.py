"""
Versioned wording of the Beitrittserklärung and the SEPA-Lastschriftmandat.

Why versioned: an online SEPA mandate puts the burden of proof on the creditor. If a member
disputes a collection years from now, the Verein must be able to show the text that was on
screen when they clicked submit - not the text that happens to be current. Every application
therefore stores a terms_version, and the archived PDF is rendered from the entry below that
matches it.

Rules for changing this file:
  - Never edit an existing version in place. Add a new dated key and point
    CURRENT_TERMS_VERSION at it.
  - Placeholders in {braces} are filled from smartdorm.config at render time, so the
    Gläubiger-ID and the Beitragshöhe stay in one place.
"""

from . import config as app_config

CURRENT_TERMS_VERSION = '2026-09-01'


MEMBERSHIP_TERMS = {
    '2026-09-01': {
        'title': 'Mitgliedsbeitritt',
        'intro': (
            'Im Folgenden kannst du deine Beitrittserklärung zum HSV e.V. sowie dein '
            'SEPA-Lastschriftmandat zum Einzug deines Mitgliedsbeitrags abgeben. '
            'Informationen zur Verarbeitung deiner Daten findest du in den '
            'Datenschutzhinweisen in der Beitrittserklärung bzw. in unserer '
            'Datenschutzerklärung.'
        ),
        'welcome': (
            'Wir freuen uns, dass du Teil der studentischen Selbstverwaltung des '
            'Schollheims sein willst!'
        ),
        'declaration_heading': 'Beitrittserklärung',
        'declaration_subheading': (
            'für den Beitritt zum Studierendenwohnheim Geschwister Scholl '
            'Heimselbstverwaltung e.V.'
        ),

        # --- Amtsliste: freiwillige, jederzeit widerrufbare Einwilligung ---
        'amtsliste_consent_label': (
            'Ich willige ein, dass mein Name, meine Zimmernummer und mein Flur, sofern ich '
            'ein Amt im Wohnheim übernehme, zu Beginn des Semesters in einer vereinsintern '
            'veröffentlichten Amtsliste aufgeführt werden. Die Einwilligung ist freiwillig '
            'und kann jederzeit mit Wirkung für die Zukunft widerrufen werden.'
        ),
        'amtsliste_decline_label': 'Keine Antwort',

        'duty_to_notify': (
            'Das Mitglied verpflichtet sich, Änderungen der Daten dem Verein unverzüglich '
            'mitzuteilen.'
        ),
        'statutes_acknowledgement': (
            'Mit dem Absenden dieser Beitrittserklärung erkenne ich die Satzung des '
            'Studierendenwohnheim Geschwister Scholl Heimselbstverwaltung e.V. sowie die '
            'Vereinsordnungen ausdrücklich an. Insbesondere habe ich Kenntnis davon, dass '
            'derzeit ein Mitgliedsbeitrag von {fee} € pro Monat erhoben wird. Ich bestätige '
            'außerdem, einen Wohnvertrag mit dem Schollheim e.V. abgeschlossen zu haben.'
        ),
        'automatic_end': (
            'Mit Beendigung des Mietverhältnisses mit dem Schollheim e.V. endet die '
            'Mitgliedschaft automatisch; einer gesonderten Austrittserklärung bedarf es nicht.'
        ),
        'privacy_notice': (
            'Datenschutzhinweis: Der HSV e.V. verarbeitet die im Rahmen der '
            'Beitrittserklärung angegebenen personenbezogenen Daten zur Durchführung der '
            'Mitgliedschaft und zur Erfüllung seiner satzungsmäßigen Aufgaben. Hierzu werden '
            'auch erforderliche ergänzende personenbezogene Bewohnerdaten vom Schollheim e.V. '
            'übernommen. Zugriff erhalten die zuständigen Organe, Referate und Ämter des '
            'HSV e.V., soweit dies zur Erfüllung ihrer jeweiligen Aufgaben erforderlich ist. '
            'Über die Aufnahme entscheiden das Zimmerreferat, das Finanzenreferat oder der '
            'Heimrat; diese haben zu diesem Zweck auch Zugriff auf die im Antrag angegebenen '
            'Zahlungsdaten. Weitere Informationen zu den verarbeiteten Daten, den '
            'Rechtsgrundlagen, Empfängern, Speicherdauern und deinen Betroffenenrechten '
            'findest du in unserer Datenschutzerklärung. Verantwortlicher ist der '
            'Studierendenwohnheim Geschwister Scholl Heimselbstverwaltung e.V., '
            'Steinickeweg 7, 80798 München, E-Mail: heimrat@schollheim.net.'
        ),

        # --- SEPA ---
        'sepa_heading': 'SEPA-Lastschriftmandat',
        'sepa_creditor': (
            'Zahlungsempfänger: {creditor_name}, {creditor_address}. '
            'Gläubiger-Identifikationsnummer: {creditor_id}'
        ),
        'sepa_mandate_reference_note': (
            'Mandatsreferenz: Wird dem Mitglied vor dem ersten Lastschrifteinzug mitgeteilt.'
        ),
        'sepa_authorisation': (
            'Hiermit ermächtige ich den Studierendenwohnheim Geschwister Scholl '
            'Heimselbstverwaltung e.V., Zahlungen von meinem Konto mittels '
            'SEPA-Basislastschrift einzuziehen. Zugleich weise ich mein Kreditinstitut an, '
            'die vom Studierendenwohnheim Geschwister Scholl Heimselbstverwaltung e.V. auf '
            'mein Konto gezogenen SEPA-Basislastschriften einzulösen. Ich kann innerhalb von '
            'acht Wochen, beginnend mit dem Belastungsdatum, die Erstattung des belasteten '
            'Betrags verlangen. Es gelten dabei die mit meinem Kreditinstitut vereinbarten '
            'Bedingungen.'
        ),
        'sepa_payment_type': (
            'Art der Zahlung: wiederkehrende Zahlung (monatlicher Mitgliedsbeitrag).'
        ),
        # Ohne diese Vereinbarung gilt die gesetzliche Frist von 14 Kalendertagen und jeder
        # einzelne Einzug müsste vorher gesondert angekündigt werden.
        'sepa_prenotification': (
            'Vorabankündigung: Der Mitgliedsbeitrag von derzeit {fee} € wird jeweils zum '
            '{collection_day}. Bankarbeitstag eines Monats eingezogen. Die Vorabankündigung '
            '(Pre-Notification) erfolgt spätestens {prenotification_days} Kalendertage vor '
            'Fälligkeit; die Frist wird hiermit gegenüber der gesetzlichen Frist von '
            '14 Kalendertagen entsprechend verkürzt. Die Ankündigung kann einmalig für alle '
            'wiederkehrenden Einzüge erfolgen.'
        ),
        'sepa_consent_label': (
            'Ich erteile hiermit das oben genannte SEPA-Lastschriftmandat und bestätige, dass '
            'ich zur Erteilung dieses Mandats berechtigt bin (Kontoinhaber:in oder '
            'bevollmächtigt).'
        ),
        'sepa_alternative_label': (
            'Ich habe zusammen mit dem Finanzenreferat eine andere Zahlungsmethode vereinbart.'
        ),
        'sepa_documentation_note': (
            'Mit dem Absenden des Formulars werden Datum und Uhrzeit der Mandatserteilung '
            'automatisch dokumentiert. Eine Rückbuchung im Rahmen des gesetzlichen '
            'Erstattungsrechts berührt nicht die Beitragspflicht aus der Mitgliedschaft.'
        ),
        'sepa_privacy_notice': (
            'Datenschutzhinweis: Ergänzend zum Datenschutzhinweis oben gilt für deine '
            'Zahlungsdaten: Die Verarbeitung erfolgt zur Erfüllung deiner Beitragspflicht aus '
            'der Mitgliedschaft. Die Erteilung des SEPA-Mandats als gewählte Zahlungsart ist '
            'freiwillig; die Beitragspflicht selbst bleibt davon unberührt. Zugriff auf die '
            'Zahlungsdaten haben innerhalb des Vereins das Finanzenreferat sowie die über die '
            'Aufnahme entscheidenden Referate, soweit dies zur Erfüllung ihrer Aufgaben '
            'erforderlich ist. Zur Durchführung der Lastschrift werden die erforderlichen '
            'Daten (insbesondere IBAN, Name, Mandatsreferenz) an die beteiligten '
            'Zahlungsdienstleister übermittelt. Zahlungsdaten werden aufgrund gesetzlicher '
            'Aufbewahrungspflichten auch nach Ende der Mitgliedschaft für die jeweils '
            'geltende Aufbewahrungsfrist gespeichert.'
        ),

        'minor_notice': (
            'Für einen Beitritt vor Vollendung des 18. Lebensjahres ist die Zustimmung der '
            'gesetzlichen Vertreter erforderlich. Bitte wende dich in diesem Fall an das '
            'Finanzenreferat oder den Heimrat - der Beitritt läuft dann über ein '
            'Papierformular.'
        ),
    },
}


def get_terms(version=None):
    """
    Return the text block for a version, with the config placeholders filled in.

    Falls back to nothing: an unknown version raises, because silently rendering a mandate
    under the wrong wording is exactly the failure this module exists to prevent.
    """
    version = version or CURRENT_TERMS_VERSION
    try:
        raw = MEMBERSHIP_TERMS[version]
    except KeyError:
        raise ValueError(f"Unbekannte Version des Erklärungstextes: {version!r}")

    placeholders = {
        # Config keeps a Decimal-parseable value; the text needs a German decimal comma.
        'fee': str(app_config.HSV_MEMBERSHIP_FEE_EUR).replace('.', ','),
        'creditor_id': app_config.HSV_CREDITOR_ID,
        'creditor_name': app_config.HSV_CREDITOR_NAME,
        'creditor_address': app_config.HSV_CREDITOR_ADDRESS,
        'collection_day': app_config.HSV_COLLECTION_DAY,
        'prenotification_days': app_config.HSV_PRENOTIFICATION_DAYS,
    }

    return {
        key: value.format(**placeholders) if isinstance(value, str) else value
        for key, value in raw.items()
    }
