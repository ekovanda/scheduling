"""Application version and business-facing release history."""

from dataclasses import dataclass

APP_NAME = "Dienstplan Generator"
CURRENT_VERSION = "1.5.2"


@dataclass(frozen=True)
class Release:
    """A concise, user-facing application release."""

    version: str
    date: str
    summary: str
    highlights: tuple[str, ...]


RELEASES: tuple[Release, ...] = (
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
