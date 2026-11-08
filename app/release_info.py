"""Application version and business-facing release history."""

from dataclasses import dataclass

APP_NAME = "Dienstplan Generator"
CURRENT_VERSION = "2.1.2"


@dataclass(frozen=True)
class Release:
    """A concise, user-facing application release."""

    version: str
    date: str
    summary: str
    highlights: tuple[str, ...]


RELEASES: tuple[Release, ...] = (
    Release(
        version="2.1.2",
        date="08. November 2026",
        summary="Korrektur der Nachtdienst-Validierung an Quartalsgrenzen",
        highlights=(
            "Nachtdienstblöcke über Quartalsgrenzen hinweg werden in der Planprüfung nun korrekt berücksichtigt.",
        ),
    ),
    Release(
        version="2.1.1",
        date="08. November 2026",
        summary="Optimierung der Anmeldeansicht",
        highlights=(
            "Login-Hinweistext zur Passworteingabe auf der Portalseite entfernt.",
        ),
    ),
    Release(
        version="2.1.0",
        date="08. November 2026",
        summary="Kompakte Fairness-Ansicht & optimierter Dienstplan",
        highlights=(
            "Fokus auf Ausgleichs-Pfeile mit natürlichem Scrollen und kliniknahen Begriffen.",
            "Übersichtlicher Dienstplan mit linksbündigen Schichtnummern und einheitlichen 'Vet'-Badges.",
            "Dezente, neutrale Wochentage und Schichtbezeichnungen in den Vorbelegungen.",
        ),
    ),
    Release(
        version="2.0.4",
        date="08. November 2026",
        summary="Kaskadierende Bereinigung gelöschter Mitarbeiter",
        highlights=(
            "Beim Löschen von Mitarbeitenden werden verknüpfte Abwesenheiten und Vorbelegungen automatisch mitbereinigt.",
            "Verhindert verwaiste Schichtbuchungen und Blockaden bei der automatischen Dienstplan-Berechnung.",
        ),
    ),
    Release(
        version="2.0.3",
        date="08. November 2026",
        summary="Zuverlässige Stammdaten-Pflege & vollständiger Excel-Export",
        highlights=(
            "Fehlermeldungen beim Speichern und Löschen werden sofort angezeigt statt ignoriert.",
            "Freie Datumswahl für 2026/2027, Abwesenheitsarten, Notizen und Status-Steuerung im Team.",
            "Vollständige Mitarbeiternamen in allen Tabellenblättern des Excel-Exports.",
        ),
    ),
    Release(
        version="2.0.2",
        date="08. November 2026",
        summary="Echte Solver-Kennzahlen, Blockabstand & Feiertagsblöcke",
        highlights=(
            "Echte Anzeige von Berechnungsdauer, Lösungsstatus und vorbelegten Schichten im Dienstplan.",
            "Einstellbarer Mindest-Blockabstand und automatische Monats-Rückstellung beim Quartalswechsel.",
            "Feiertags-Ruhezeitverkürzung greift zuverlässig auch an Folgetagen mehrtägiger Nachtblöcke.",
        ),
    ),
    Release(
        version="2.0.1",
        date="08. November 2026",
        summary="Korrektur Excel-Export, Umlaut-Kürzel & Fairness-Soll",
        highlights=(
            "Zuverlässiger Excel-Export des Dienstplans auch bei aktivem Passwortschutz.",
            "Keine falschen Musterdaten mehr bei leeren Listen sowie Unterstützung für Umlaute in Kürzeln.",
            "Inaktive Mitarbeitende ohne Schichten verfälschen nicht mehr den Gruppendurchschnitt der Fairness.",
        ),
    ),
    Release(
        version="2.0.0",
        date="08. November 2026",
        summary="Plattform-Modernisierung & React Single Source of Truth",
        highlights=(
            "Moderne Webanwendung mit interaktiver Dienstplan-, Mitarbeiter- und Abwesenheitsverwaltung.",
            "Schneller, asynchroner Optimierungsserver mit Echtzeit-Fortschritt und Vorab-Prüfung.",
            "Zentraler Speicher für Klinikdaten ohne manuelle Tabellen-Uploads und Datenverlust.",
        ),
    ),
    Release(
        version="1.13.3",
        date="08. November 2026",
        summary="Bearbeitung für Abwesenheiten & Vorbelegungen",
        highlights=(
            "Neuer Bearbeiten-Button (Stift-Symbol) für bestehende Einträge in beiden Ansichten.",
            "Formulardialoge öffnen mit vorhandenen Daten zur schnellen Anpassung.",
            "Direkte Aktualisierung im Frontend und REST-API-Abgleich via PUT-Endpunkten.",
        ),
    ),
    Release(
        version="1.13.2",
        date="08. November 2026",
        summary="Dienstplan: Angepinnte Legende & Schichtnummerierung",
        highlights=(
            "Mitarbeiternamen im Vordergrund; Schichten kompakt als (1) bis (4) nummeriert.",
            "Angepinnte Schicht-Legende bleibt beim vertikalen Scrollen dauerhaft sichtbar.",
            "Intern-Tagdienst auf Person fokussiert ohne redundante Zeit- und Rollenanzeige.",
        ),
    ),
    Release(
        version="1.13.1",
        date="08. November 2026",
        summary="Vorbelegungs-Kacheln & Wochentagsanzeige",
        highlights=(
            "Interaktive Schicht-Kacheln zur direkten Auswahl tagesabhängiger Dienste statt Dropdown.",
            "Neue Tabellenspalte für Wochentage zur schnellen Prüfung des Dienstkontexts.",
            "Leeres Datumsfeld mit automatischer Kalenderöffnung im Planungsjahr 2027.",
        ),
    ),
    Release(
        version="1.13.0",
        date="08. November 2026",
        summary="UI-Fokussierung, Sofortsuche & Dienstplan-Neugestaltung",
        highlights=(
            "Neue Sofortsuche und Autocomplete-Auswahl für Mitarbeiter in Formularen und Abwesenheiten.",
            "Fokussierte Ansichten nach Person (Abwesenheiten) und reine Listenansicht (Vorbelegungen).",
            "Dienstplan mit neuer Spaltenaufteilung für Tag/Rufbereitschaft und Interns sowie grüner Vorbelegung.",
        ),
    ),
    Release(
        version="1.12.5",
        date="08. November 2026",
        summary="Skalierbarkeit, Concurrency & Solver-Transparenz",
        highlights=(
            "Single-Worker Cloud Run Topologie zur Absicherung aktiver Hintergrund-Optimierungen.",
            "Globale Nebenläufigkeitsbegrenzung (429) und CPU-Thread-Deckelung für 2-vCPU Instanzen.",
            "Transparente Dokumentation von Solver-Status, Best-Bound und Optimalitätslücke.",
        ),
    ),
    Release(
        version="1.12.4",
        date="08. November 2026",
        summary="Stammdaten-Validierung & Abteilungs-Grenzschutz",
        highlights=(
            "Strenge API- und Datenmodell-Validierung für Mitarbeiter und Identifikatoren.",
            "Vermeidung fehlerhafter Kennzahlen und Duplikate bei Einzel- und Massenimport.",
            "Abteilungs-Trennung für OP und Station über Quartalsgrenzen hinweg (H17/H18).",
        ),
    ),
    Release(
        version="1.12.3",
        date="08. November 2026",
        summary="Dienstplan-Horizont, Schichtabdeckung & Feiertage",
        highlights=(
            "Exakte Kalenderquartal-Horizonte ohne Schicht-Überlappung oder Auslassung.",
            "Strikte Schichtabdeckungs-Garantie und Validierungs-Prüfung nach Optimierung.",
            "Validierung vorab zugewiesener Schichten und Persistierung des Feiertags-Status.",
        ),
    ),
    Release(
        version="1.12.2",
        date="08. November 2026",
        summary="Sicherheits-Härtung: Sessions, Pfade & Container",
        highlights=(
            "12-Stunden Token-Ablauf, Scrypt-Kennwortschutz und Brute-Force-Drosselung.",
            "Pfad-Validierung gegen Directory Traversal und Isolierung von Entwickler-Daten.",
            "Vollständiger Ausschluss sensibler Klinikdaten aus Container-Builds.",
        ),
    ),
    Release(
        version="1.12.1",
        date="08. November 2026",
        summary="Sicherheits-Härtung der API & Passwort-Schutz",
        highlights=(
            "Alle Lese- und Berechnungs-Endpunkte erfordern verifizierte Planer-Berechtigung.",
            "Entfernung des Standard-Passworts und Absicherung gegen unkonfigurierte Deployments.",
        ),
    ),
    Release(
        version="1.12.0",
        date="07. November 2026",
        summary="Produktions-Cutover & Firebase Hosting Pipeline",
        highlights=(
            "Vollständiger Cloud Run Cutover auf die moderne React- & FastAPI-Architektur.",
            "Firebase Hosting CDN-Routing mit Sub-10ms Edge-Caching und API-Proxy nach Frankfurt.",
            "Automatisierte Deployment-Pipelines für Linux und Windows mit sofortiger Rollback-Möglichkeit.",
        ),
    ),
    Release(
        version="1.11.0",
        date="07. November 2026",
        summary="Planer-Authentifizierung & Reibungsloser Dev-Login",
        highlights=(
            "Geschützte Planer-Sitzungen sichern Stammdaten, Abwesenheiten und Solver-Ausführung ab.",
            "Reibungsloser Entwicklungsmodus: Automatischer Bypass oder 1-Klick-Login bei lokalen Tests.",
            "Direkte Abmeldung im Header und automatische Token-Verwaltung in allen API-Abfragen.",
        ),
    ),
    Release(
        version="1.10.0",
        date="07. November 2026",
        summary="Machbarkeits-Prüfung & Diagnose bei Planungs-Konflikten",
        highlights=(
            "1-Klick-Machbarkeitsprüfung erkennt Vorbelegungs- und Sperrkonflikte vor dem Solver-Start.",
            "Verständliche Diagnosekarten mit konkreten Lösungsvorschlägen bei unlösbaren Konstellationen.",
            "Vermeidet Fehlberechnungen bei Doppelbelegungen, Urlaubskollisionen und Mindest-Ruhezeiten.",
        ),
    ),
    Release(
        version="1.9.0",
        date="07. November 2026",
        summary="Vorher-Nachher Ausgleichs-Pfeile & Fairness-Vektoren",
        highlights=(
            "Interaktiver Vektor-Plot zeigt Vorher- und Nachher-Stand jeder Person mit dynamischen Ausgleichspfeilen.",
            "Direkte Erfolgsmetriken für die Quote verbesserter Mitarbeiter und den Abbau der Unwucht.",
            "Wahl zwischen Einzel-Dumbbell-Vektoren je Mitarbeiter und globalem Konvergenz-Trichter.",
        ),
    ),
    Release(
        version="1.8.0",
        date="07. November 2026",
        summary="Transparente Fairness-Übersicht & L1-Ausgleichsoptimierung",
        highlights=(
            "Transparente 3-Spalten-Fairness: Plan vs. Soll, Vorquartals-Saldo und Netto-Gesamtsaldo je Berufsgruppe.",
            "Interaktives Fairness-Dashboard mit Balance-Balken, 2D-Ausgleichs-Scatterplot und Dichte-Streifen.",
            "L1-Summenfairness im Solver kompensiert Vorquartals-Salden gezielt über das gesamte Team.",
        ),
    ),
    Release(
        version="1.7.0",
        date="06. November 2026",
        summary="Dienstplan-Verschlankung, Smart-Stop & Personal-Flow",
        highlights=(
            "Kliniknahe Begriffe ('Dienstplan', 'Vorquartal & Ausgleich') und direkter Start im Planer.",
            "Personalverwaltung mit 1-Klick-Nachtdienst, Wochentag-Filter und schlanker Abteilungsanzeige.",
            "CP-SAT Smart-Stop mit bis zu 10 Min. Suchdauer und echter Anzeige von Rufbereitschaft & Paaren.",
        ),
    ),
    Release(
        version="1.6.0",
        date="06. November 2026",
        summary="Web-Plattform, 2027-Q1 Baseline & Feiertagsdienste",
        highlights=(
            "Zentrale Web-Plattform mit direkter Datenhaltung für Personal, Abwesenheiten und Quartalspläne.",
            "Automatische Übernahme von Vorquartals-Einsätzen (Q4 2026) für faire Verteilung und Ruhezeiten.",
            "Vorgegebene Feiertagsdienste werden vorab auf Konflikte geprüft und verlässlich integriert.",
        ),
    ),
    Release(
        version="1.5.2",
        date="02. November 2026",
        summary="Korrektur Intern-Wochenendzählung & Fairness",
        highlights=(
            "Intern-Wochenenden (Sa+So) werden als 1 Wochenenddienst statt 2 Einzelschichten gezählt.",
            "Fairness-Übersichten und Spread-Metriken zeigen für Interns reale Wochenenden.",
        ),
    ),
    Release(
        version="1.5.1",
        date="01. November 2026",
        summary="Rollen-Klarstellung Vets/Interns & Eingabeprüfung",
        highlights=(
            "Eindeutige Rollentrennung: Vets (Entlastung) und Interns (Ausbildung) in Kalender und Auswertungen.",
            "Strengere Prüfung von Personaldateien verhindert unvollständige Zeilen ohne Arbeitszeit.",
        ),
    ),
    Release(
        version="1.5.0",
        date="01. November 2026",
        summary="Offene Nächte, Intern-Wochenenden & Vet-Entlastung",
        highlights=(
            "Offene Nächte (So-Mo, Mo-Di) mit 2er-Besetzung (mind. 1 TFA) und geschlossene Nächte.",
            "Interns übernehmen gekoppelte Wochenend-Paare (Sa_Intern & So_Intern) mit 2-Track-Fairness.",
            "Vets entlasten das TFA-Team an Di-Do in 2er-Blöcken im Alleindienst (1x/2 Monate).",
        ),
    ),
    Release(
        version="1.2.0",
        date="31. Juli 2026",
        summary="Hinweise auf Ausnahmen an Quartalsgrenzen",
        highlights=(
            "Ausnahmen beim Dienstblock-Abstand zum Vorquartal sind im Kalender sofort mit einem Warnsymbol erkennbar.",
            "Eine Detailansicht zeigt betroffene Mitarbeitende sowie den tatsächlichen und erforderlichen Abstand.",
            "Der Excel-Export bleibt unverändert und enthält keine zusätzlichen Hinweiskennzeichen.",
        ),
    ),
    Release(
        version="1.1.0",
        date="31. Juli 2026",
        summary="Versionsinfo und Änderungsverlauf",
        highlights=(
            "Eine eigene Infoseite zeigt die installierte Version und die wichtigsten Weiterentwicklungen.",
            "Der Versionsverlauf erläutert den praktischen Nutzen der Änderungen für die Dienstplanung.",
        ),
    ),
    Release(
        version="1.0.3",
        date="12. Juli 2026",
        summary="Feiertagsdienste am Wochenende",
        highlights=(
            "Vorgegebene Dienste werden auch dann zuverlässig übernommen, wenn ein Feiertag auf ein Wochenende fällt.",
            "So bleiben extern abgestimmte oder bereits festgelegte Einsätze im fertigen Plan erhalten.",
        ),
    ),
    Release(
        version="1.0.2",
        date="31. Mai 2026",
        summary="Vorquartal-Import und Excel-Export",
        highlights=(
            "Der vorherige Quartalsplan kann aus dem Excel-Export übernommen werden, damit die Verteilung über Quartalsgrenzen hinweg fair bleibt.",
            "Neue Mitarbeitende, vorgegebene Feiertagsdienste und geplante Eintrittsdaten werden bei der Planung berücksichtigt.",
            "Excel-Exporte trennen Nacht- und Wochenenddienste übersichtlich und lassen sich wieder einlesen.",
        ),
    ),
    Release(
        version="1.0.1",
        date="31. Mai 2026",
        summary="Kapazitätsprüfung und Planfortschritt",
        highlights=(
            "Vor der Berechnung zeigt eine Kapazitätsprüfung frühzeitig, ob ausreichend Personal verfügbar ist.",
            "Der Fortschritt und mögliche Gründe für einen nicht erstellbaren Plan sind besser nachvollziehbar.",
            "Für unterschiedliche Situationen kann zwischen einer schnellen und einer gründlichen Berechnung gewählt werden.",
        ),
    ),
    Release(
        version="1.0.0",
        date="24. März 2026",
        summary="Erste produktive Nutzung",
        highlights=(
            "Erste produktive Nutzung der Anwendung zur Erstellung von Quartalsplänen.",
            "Datei-Importe akzeptieren unterschiedliche, praxisnahe Spaltenbezeichnungen und reduzieren den manuellen Vorbereitungsaufwand.",
            "Vorgegebene Dienste können vor der Planung hinterlegt werden, damit verbindliche Absprachen berücksichtigt bleiben.",
        ),
    ),
    Release(
        version="0.3.0",
        date="20. Februar 2026",
        summary="Passwortschutz und Planprüfung",
        highlights=(
            "Optionaler Passwortschutz begrenzt den Zugriff auf die Planungsdaten.",
            "Die Fairness-Auswertung wurde verständlicher aufbereitet und hilft bei der gemeinsamen Planprüfung.",
        ),
    ),
    Release(
        version="0.2.0",
        date="31. Januar 2026",
        summary="Regeln und faire Verteilung",
        highlights=(
            "Die Planung berücksichtigt verbindliche Dienst-, Pausen- und Qualifikationsregeln.",
            "Dienste werden nach Arbeitszeit fair verteilt und sind in einer verbesserten Kalenderansicht prüfbar.",
        ),
    ),
    Release(
        version="0.1.0",
        date="25. Januar 2026",
        summary="Interner Planungs-Prototyp",
        highlights=(
            "Erste interne Version zur Erstellung von Quartalsplänen für Nacht- und Wochenenddienste.",
            "Sie bildete die Grundlage für die spätere produktive Nutzung.",
        ),
    ),
)
