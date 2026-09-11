Refactoring:

- Modifiche in cli:
    - modificato/aggiunto qualche commento
    - creato il file color.py
        - uniformati tutti i file in cli per il suo utilizzo
        - creato un modo unico per controllare se il terminale supporti i colori o meno, con relativo failover
    - sistemato il fallback della ventola, l'ho rimosso, inutilmente confusionario

- Modifiche in daemon:
    - Refactoring dato dalla rimozione del fallback della ventola
    - Semplificato l'over-ingegnerizato controllo versione