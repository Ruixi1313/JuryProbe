# Attribute Corruption Pool v3 N=300 Author Audit

Date: 2026-06-11

Dataset: `data/attribute_corruption_pool_v3_n300.jsonl`

Source frame: `data/frozen/attribute_v2/attribute_pool_v2.jsonl`

Sampling seed: 42

Audit sample seed: 20260611

Audit size: 50 items (25 clean, 25 corrupted)

Construction change from v2: v3 uses `balanced_v3` replacement policy with
`replacement_pair_cap = 20` to reduce template concentration while preserving
the same strict Attribute candidate pool and validation gates.

## Verdict

PENDING author audit.

This audit decides whether Attribute v3 is stable enough for confirmatory
judge evaluation. If recurring construction artifacts remain, stop Attribute
as a confirmatory family rather than tuning another version.

## Pass Criteria

Green Light:

- At most 5 bad samples out of 50.
- Continue to freeze Attribute v3 and run judge evaluation.

Yellow Light:

- 6 to 8 bad samples out of 50.
- Continue only if bad samples are dispersed across artifact types rather than
  concentrated in one recurring construction problem.

Red Light:

- More than 8 bad samples out of 50, or at least 5 samples with the same
  artifact type.
- Stop Attribute as a confirmatory family. Do not tune another construction
  version by default; report Attribute as a construction audit and focus the
  main evaluation on Number and Entity.

Per-item validity criteria:

- Attribute replacement preserves the same subject and changes only a
  descriptive attribute such as nationality, occupation, genre, language, or
  type.
- The modified claim is clearly false, not merely uncertain or still plausible.
- The corruption does not replace a named entity or title token.
- The modified claim remains fluent and does not introduce article, word order,
  or naturalness artifacts.

## Audit Codes

- `VALID`: usable as constructed.
- `TYPO_SOURCE`: original claim contains a typo or source artifact that makes
  the item unsuitable.
- `FLUENCY_ARTIFACT`: modified claim introduces article, word order, or
  naturalness artifacts.
- `ATTRIBUTE_SPACE_MISMATCH`: replacement crosses an unsuitable attribute
  space, changes a title/entity-like token, or no longer functions as the same
  kind of subject attribute.
- `AMBIGUOUS_FACT`: original or corrupted claim is too broad, uncertain, still
  plausible, or not clearly verifiable as true/false.
- `TEMPLATE_BIAS`: item reflects an over-concentrated replacement template or
  repetitive construction pattern that may bias the family.
- `OTHER`: explain briefly.

## Clean Sample

### Clean 01

- id: `attrv3_0276`
- source_claim_id: `fever_151795:attr1`
- attribute_type: `occupation`
- statement: Bradley Whitford is an actor that stars in the movie Get Out.
- audit_code: VALID
- notes: 

### Clean 02

- id: `attrv3_0144`
- source_claim_id: `fever_195592:attr1`
- attribute_type: `nationality`
- statement: Joy is an American biographical film.
- audit_code: VALID
- notes: 

### Clean 03

- id: `attrv3_0226`
- source_claim_id: `fever_142838:attr1`
- attribute_type: `genre`
- statement: Galaxy Quest is a comedy movie.
- audit_code: VALID
- notes: 

### Clean 04

- id: `attrv3_0260`
- source_claim_id: `fever_131408:attr1`
- attribute_type: `genre`
- statement: Transformers (film) is an American science fiction  film.
- audit_code: VALID
- notes: 

### Clean 05

- id: `attrv3_0275`
- source_claim_id: `fever_21329:attr1`
- attribute_type: `nationality`
- statement: Hannah Simone was a Canadian fashion model.
- audit_code: VALID
- notes: 

### Clean 06

- id: `attrv3_0294`
- source_claim_id: `fever_150055:attr1`
- attribute_type: `occupation`
- statement: Tori Kelly is an American singer.
- audit_code: VALID
- notes: 

### Clean 07

- id: `attrv3_0116`
- source_claim_id: `fever_103736:attr1`
- attribute_type: `nationality`
- statement: The X Factor is a British competition.
- audit_code: VALID
- notes: Slightly broad category ("competition"), but still a valid factual attribute.

### Clean 08

- id: `attrv3_0065`
- source_claim_id: `fever_200620:attr1`
- attribute_type: `occupation`
- statement: Geoffrey Beevers worked as an actor at the Orange Tree Theatre.
- audit_code: VALID
- notes: 

### Clean 09

- id: `attrv3_0078`
- source_claim_id: `fever_197932:attr1`
- attribute_type: `genre`
- statement: Until Dawn is a horror game.
- audit_code: VALID
- notes: 

### Clean 10

- id: `attrv3_0005`
- source_claim_id: `fever_112969:attr1`
- attribute_type: `nationality`
- statement: Jules Henri Poincare was a French mathematician and theoretical physicist.
- audit_code: VALID
- notes: 

### Clean 11

- id: `attrv3_0019`
- source_claim_id: `fever_2621:attr1`
- attribute_type: `occupation`
- statement: Maria Sharapova is a tennis player.
- audit_code: VALID
- notes: 

### Clean 12

- id: `attrv3_0027`
- source_claim_id: `fever_189072:attr1`
- attribute_type: `nationality`
- statement: Adam West is an American citizen.
- audit_code: VALID
- notes: 

### Clean 13

- id: `attrv3_0234`
- source_claim_id: `fever_67989:attr1`
- attribute_type: `occupation`
- statement: Ty Cobb was a baseball player.
- audit_code: VALID
- notes: 

### Clean 14

- id: `attrv3_0011`
- source_claim_id: `fever_88611:attr1`
- attribute_type: `nationality`
- statement: Dan Martin is an Irish professional road cyclist.
- audit_code: VALID
- notes: 

### Clean 15

- id: `attrv3_0112`
- source_claim_id: `fever_117362:attr1`
- attribute_type: `occupation`
- statement: Mithun Chakraborty is an actor who has starred in the movie 'Disco Dancer'.
- audit_code: VALID
- notes: 

### Clean 16

- id: `attrv3_0251`
- source_claim_id: `fever_152778:attr1`
- attribute_type: `nationality`
- statement: The Ten Commandments is an American biblical film.
- audit_code: VALID
- notes: 

### Clean 17

- id: `attrv3_0230`
- source_claim_id: `fever_59799:attr1`
- attribute_type: `occupation`
- statement: Lay (entertainer) is a Chinese actor.
- audit_code: VALID
- notes: 

### Clean 18

- id: `attrv3_0263`
- source_claim_id: `fever_5218:attr1`
- attribute_type: `occupation`
- statement: Felicity Huffman is an actress who is best known for her role in the comedy-drama and mystery series Desperate Housewives.
- audit_code: VALID
- notes: 

### Clean 19

- id: `attrv3_0151`
- source_claim_id: `fever_117955:attr1`
- attribute_type: `nationality`
- statement: Heather Watson is a British citizen.
- audit_code: VALID
- notes: 

### Clean 20

- id: `attrv3_0174`
- source_claim_id: `fever_217921:attr1`
- attribute_type: `occupation`
- statement: Lucy Liu  is an American actress that was involved with Kung Fu Panda 3.
- audit_code: VALID
- notes: Minor double-space before "is", but not a source-quality issue.

### Clean 21

- id: `attrv3_0286`
- source_claim_id: `fever_155136:attr1`
- attribute_type: `occupation`
- statement: Jennifer Aniston's father was an actor.
- audit_code: VALID
- notes: 

### Clean 22

- id: `attrv3_0155`
- source_claim_id: `fever_57726:attr1`
- attribute_type: `genre`
- statement: The Adjustment Bureau is an American science fiction thriller movie released in 2011.
- audit_code: VALID
- notes: 

### Clean 23

- id: `attrv3_0235`
- source_claim_id: `fever_49767:attr1`
- attribute_type: `occupation`
- statement: Travis Barker is an American musician.
- audit_code: VALID
- notes: 

### Clean 24

- id: `attrv3_0114`
- source_claim_id: `fever_101302:attr1`
- attribute_type: `nationality`
- statement: Katie Stevens is an American citizen.
- audit_code: VALID
- notes: 

### Clean 25

- id: `attrv3_0293`
- source_claim_id: `fever_207420:attr1`
- attribute_type: `nationality`
- statement: Elizabeth Meriwether is an American television showrunner.
- audit_code: VALID
- notes: 

## Corrupted Sample

### Corrupted 01

- id: `attrv3_0572`
- source_claim_id: `fever_99487:attr1`
- attribute_type: `nationality`
- original: The Council on Foreign Relations is American.
- corrupted: The Council on Foreign Relations is Chinese.
- replacement: `American` -> `Chinese`
- audit_code: VALID
- notes: 

### Corrupted 02

- id: `attrv3_0317`
- source_claim_id: `fever_206536:attr1`
- attribute_type: `nationality`
- original: Joseph Barbera was an American animator.
- corrupted: Joseph Barbera was an Israeli animator.
- replacement: `American` -> `Israeli`
- audit_code: VALID
- notes: 

### Corrupted 03

- id: `attrv3_0557`
- source_claim_id: `fever_161495:attr1`
- attribute_type: `nationality`
- original: Robbie Collin is a British man.
- corrupted: Robbie Collin is a Canadian man.
- replacement: `British` -> `Canadian`
- audit_code: VALID
- notes: 

### Corrupted 04

- id: `attrv3_0372`
- source_claim_id: `fever_182630:attr1`
- attribute_type: `nationality`
- original: Kris Wu is a Chinese-born Canadian singer.
- corrupted: Kris Wu is a Danish-born Canadian singer.
- replacement: `Chinese` -> `Danish`
- audit_code: VALID
- notes: 

### Corrupted 05

- id: `attrv3_0467`
- source_claim_id: `fever_206529:attr1`
- attribute_type: `nationality`
- original: Joseph Barbera was an American cartoon artist.
- corrupted: Joseph Barbera was an Indian cartoon artist.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 06

- id: `attrv3_0389`
- source_claim_id: `fever_32742:attr1`
- attribute_type: `nationality`
- original: Robert Lee Yates is an American.
- corrupted: Robert Lee Yates is an Irish.
- replacement: `American` -> `Irish`
- audit_code: VALID
- notes: 

### Corrupted 07

- id: `attrv3_0509`
- source_claim_id: `fever_199620:attr1`
- attribute_type: `nationality`
- original: Black Mirror is a British fiction series.
- corrupted: Black Mirror is a Japanese fiction series.
- replacement: `British` -> `Japanese`
- audit_code: VALID
- notes: 

### Corrupted 08

- id: `attrv3_0451`
- source_claim_id: `fever_159983:attr1`
- attribute_type: `nationality`
- original: In & Out is an American comedic film.
- corrupted: In & Out is an Indian comedic film.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 09

- id: `attrv3_0309`
- source_claim_id: `fever_91355:attr1`
- attribute_type: `occupation`
- original: Elizabeth Banks is an American actress.
- corrupted: Elizabeth Banks is an American singer.
- replacement: `actress` -> `singer`
- audit_code: VALID
- notes: 

### Corrupted 10

- id: `attrv3_0404`
- source_claim_id: `fever_29084:attr1`
- attribute_type: `genre`
- original: Diary of the Dead is a horror film.
- corrupted: Diary of the Dead is a fantasy film.
- replacement: `horror` -> `fantasy`
- audit_code: VALID
- notes: 

### Corrupted 11

- id: `attrv3_0334`
- source_claim_id: `fever_192550:attr1`
- attribute_type: `nationality`
- original: Francois de Belleforest translated the works of Antonio de Guevara and he was French.
- corrupted: Francois de Belleforest translated the works of Antonio de Guevara and he was Canadian.
- replacement: `French` -> `Canadian`
- audit_code: VALID
- notes: 

### Corrupted 12

- id: `attrv3_0526`
- source_claim_id: `fever_182650:attr1`
- attribute_type: `nationality`
- original: Kris Wu is a Chinese-born Canadian actor.
- corrupted: Kris Wu is a Brazilian-born Canadian actor.
- replacement: `Chinese` -> `Brazilian`
- audit_code: VALID
- notes: 

### Corrupted 13

- id: `attrv3_0374`
- source_claim_id: `fever_20235:attr1`
- attribute_type: `genre`
- original: Hotel Transylvania is an American comedy film.
- corrupted: Hotel Transylvania is an American science fiction film.
- replacement: `comedy` -> `science fiction`
- audit_code: VALID
- notes: 

### Corrupted 14

- id: `attrv3_0475`
- source_claim_id: `fever_123174:attr1`
- attribute_type: `nationality`
- original: Charles Marie de La Condamine was a French mathematician.
- corrupted: Charles Marie de La Condamine was a Spanish mathematician.
- replacement: `French` -> `Spanish`
- audit_code: VALID
- notes: 

### Corrupted 15

- id: `attrv3_0586`
- source_claim_id: `fever_188217:attr1`
- attribute_type: `genre`
- original: The Bostonians (film) is a drama creative work.
- corrupted: The Bostonians (film) is a fantasy creative work.
- replacement: `drama` -> `fantasy`
- audit_code: VALID
- notes: 

### Corrupted 16

- id: `attrv3_0408`
- source_claim_id: `fever_210235:attr1`
- attribute_type: `occupation`
- original: William McKinley was an American politician.
- corrupted: William McKinley was an American musician.
- replacement: `politician` -> `musician`
- audit_code: VALID
- notes: 

### Corrupted 17

- id: `attrv3_0335`
- source_claim_id: `fever_161884:attr1`
- attribute_type: `occupation`
- original: Britney Spears is an American actress.
- corrupted: Britney Spears is an American director.
- replacement: `actress` -> `director`
- audit_code: VALID
- notes: 

### Corrupted 18

- id: `attrv3_0449`
- source_claim_id: `fever_213365:attr1`
- attribute_type: `nationality`
- original: Donnie Wahlberg is an American record producer.
- corrupted: Donnie Wahlberg is an Irish record producer.
- replacement: `American` -> `Irish`
- audit_code: VALID
- notes: 

### Corrupted 19

- id: `attrv3_0424`
- source_claim_id: `fever_51358:attr1`
- attribute_type: `nationality`
- original: BYD Auto is a Chinese company.
- corrupted: BYD Auto is a Greek company.
- replacement: `Chinese` -> `Greek`
- audit_code: VALID
- notes: 

### Corrupted 20

- id: `attrv3_0564`
- source_claim_id: `fever_221864:attr1`
- attribute_type: `nationality`
- original: The Narrows is an American film.
- corrupted: The Narrows is an Australian film.
- replacement: `American` -> `Australian`
- audit_code: VALID
- notes: 

### Corrupted 21

- id: `attrv3_0412`
- source_claim_id: `fever_66028:attr1`
- attribute_type: `type`
- original: Didier Drogba is a professional footballer.
- corrupted: Didier Drogba is a professional tennis player.
- replacement: `professional footballer` -> `professional tennis player`
- audit_code: VALID
- notes: 

### Corrupted 22

- id: `attrv3_0315`
- source_claim_id: `fever_19025:attr1`
- attribute_type: `nationality`
- original: Home Alone is an American film.
- corrupted: Home Alone is an Indian film.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 23

- id: `attrv3_0415`
- source_claim_id: `fever_88648:attr1`
- attribute_type: `nationality`
- original: Adi Shankar is an American film director and producer that was born in India.
- corrupted: Adi Shankar is an Indian film director and producer that was born in India.
- replacement: `American` -> `Indian`
- audit_code: AMBIGUOUS_FACT
- notes: The corruption changes nationality, but the resulting statement may remain partially plausible because the subject is explicitly described as born in India. This introduces ambiguity between nationality, origin, and identity rather than a clean factual contradiction.

### Corrupted 24

- id: `attrv3_0363`
- source_claim_id: `fever_168728:attr1`
- attribute_type: `nationality`
- original: The Ten Commandments (1956 film) is an American film.
- corrupted: The Ten Commandments (1956 film) is an Israeli film.
- replacement: `American` -> `Israeli`
- audit_code: VALID
- notes: 

### Corrupted 25

- id: `attrv3_0352`
- source_claim_id: `fever_196239:attr1`
- attribute_type: `genre`
- original: The Prince of Egypt is a drama film.
- corrupted: The Prince of Egypt is a mystery film.
- replacement: `drama` -> `mystery`
- audit_code: VALID
- notes: 
