
using branstorming dorim :
Context 
- am realizat un folder nou pt un client - EuroProject
- am uploadat un fisier PDF , si fisierul json di_referinta ( de la el pronim mereu - va fi inputul realizat cu Microsofy document extractor inteligente )
- fisierul va fi de forma Lista-oferta.docx , 
- vom realiza o varianta PDF , un docx , si una xls , formatul capul de tabel so regurile vor fi identice.
- pipeline va intreba ce client , - ce fisier dorim sa transformam ( va intreva care este numele jsonului de transformat )
    obs , acum diar pt acest clinet si pt etape de dezvoltare avem si pdf in acest foelder cum firm realiaza UAT 
- datele din fisierele PDF primite si template-ul lor nu vopr fi generate de acelsi soft , din acesta causza nu acem un template predefinit.

- vom reutiuliza din pipeline de multu - client - agentii de deterninare pagini , determinare deviz ( grupuri ) - extragere articole , - extragem inclusib preturile , si totaluriel.
- partea de devize are aceea regula , este compus din cele trei elemente - trebuie extrase ,
- vom gasi reguli de autoverificare
 - facem un caount , cate devize avem  
  - nr_crt din fiecare deviz - sa fie in ordine - sa nu am gap-uri - daca se gasesc infornatii in pdf sursa cate articole sunt / deviz - verifica si fixam pana resusim 
  - in orice varianat fiecare articol are un pret  , si avem un total general per foiecare deviz, 
    - cand generam rezultatu,l , adaugamn un layer de autoverificare 
      - daca totaul nu etse egal cu cel extras , atunci de realizeaza diferenta se indetifica articile lispsa ,m se incearca fixarea extrageri si again , again, 
        - daca dupa 5 iteratii nu avem egalitate , atunci , in raportul generat marcacm cu rosu, acesta ingelizate pt a indica utilizatorul sa explorea manaul problema 


