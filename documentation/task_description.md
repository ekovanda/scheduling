# Aufgabenstellung / Ziel
- Es geht darum ca. 24 TFAs, 9 Azubis und 4 TÄ fair auf Notdienste zu verteilen (Wochenenden und Nachtdienste) 
- Folgende Dienste gibt es
	- Samstags gibt es 3 verschiedene Dienste, die immer vergeben sein müssen
		- 10-21 Uhr (teilweise Rufbereitschaft)
			- 10-14 Uhr Anmeldung; 14-21 Uhr Rufbereitschaft
			- Kann von Azubi gemacht werden, wenn an Anmeldung eingearbeitet (präferiert TFA)
		- 10-22 Uhr (Rufbereitschaft)
		- 10-19 Uhr (Azubidienst) → Muss von Azubis gemacht werden, wenn nicht an Anmeldung eingearbeitet
	- Sonntags gibt es 3 Dienste, die immer vergeben sein müssen
		- 8-20 Uhr
		- 10-22 Uhr (Rufbereitschaft)
		- 8-20:30 Uhr (Azubi, teilweise Rufbereitschaft)
			- 8-12 Uhr vor Ort
			- 12-20:30 Rufbereitschaft
			- Wenn Azubi, dann hier
			- Azubi >18 Jahre
	- Nachtdienste
		- Muss an 7 Nächten pro Woche vergeben werden
			- Sonntag auf Montag: 1 TFA
			- Montag auf Dienstag: 1 TFA
			- Sonst 1-2 TFA siehe unten
		- MA-Präferenzen
			- Manche MA machen keine Nachtdienste
			- Manche MA machen nur zu zweit Nachtdienste → diese müssen doppelt so viele machen, wie diejenigen die sie allein machen
				- Außer Sonntag auf Montag und Montag auf Dienstag. Da ist ein TA vor Ort.
			- Manche MA machen nur alleine Nachtdienste
			- Manche MA machen nur am Wochenende Nachtdienste (eventuell auch nur zu zweit, siehe oben)
			- Azubis können keinen Nachtdienst machen, wenn sie am nächsten Tag Schule haben (eventuell ausklammern)
			- Anzahl der Nächte am Stück ist pro Mitarbeiter individuell zu erfüllen 
		- MA die Nachtdienst haben, dürfen nicht am gleichen Tag oder Folgetag Tagdienst haben
- Anzahl der Notdienste ist proportional zur Wochenarbeitszeit
- Wenn ein Azubi <18 ist, muss dieser mehr Samstagdienste haben als andere (da dieser nicht Sonntags arbeiten darf)
- Anzahl der Nachdienste muss gleich verteilt sein (innerhalb der Azubis und Nicht-Azubis)
- Anzahl der Wochenenddienste muss gleich verteilt sein (innerhalb der Azubis und Nicht-Azubis)
- Nur ein Notdienstblock pro drei Wochen
- TA 
	- machen immer allein und immer 2 Nächte pro Monat
	- TA machen kein Wochenende 
- Ziel: Quartalsweise Planung
- Idealerweise Urlaubsverfügbarkeit berücksichtigen
- Hinweis: MA Informationen könnten sich unterjährig ändern (z.B. Volljährigkeit, Anmeldungsfähigkeit, Azubistatus)
- Azubis machen ND nie alleine

# Beispielmitarbeiter
```Python
@dataclass
class MA:
	name: Julia Hausmann
	identifier: Jul 
	adult: true 
	hours: 20
	beruf: TFA #Azubi, TA
	reception: true
	nd_possible: true
	nd_alone: true
	nd_count: 1
	nd_exceptions: [1,2,3,4,6,7]