# Attribute Corruption Pool v2 N=300 Author Audit

Date: 2026-06-11

Dataset: `data/attribute_corruption_pool_v2_n300.jsonl`

Source frame: `data/frozen/attribute_v2/attribute_pool_v2.jsonl`

Sampling seed: 42

Audit sample seed: 20260611

Audit size: 50 items (25 clean, 25 corrupted)

## Verdict

PENDING author audit.

This audit decides whether Attribute v2 is stable enough for confirmatory
judge evaluation. If recurring construction artifacts appear, do not tune
another version by default; leave Attribute as a construction audit and
report Number and Entity as the confirmatory families.

## Pass Criteria

Green Light:

- At most 5 bad samples out of 50.
- Continue to freeze Attribute v2 and run judge evaluation.

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

- id: `attrv2_0276`
- source_claim_id: `fever_65848:attr1`
- attribute_type: `occupation`
- statement: Jordan Spence is an English footballer.
- audit_code: VALID
- notes: Clear occupation claim. Subject and attribute are unambiguous. No fluency or source-quality issues.

### Clean 02

- id: `attrv2_0144`
- source_claim_id: `fever_195592:attr1`
- attribute_type: `nationality`
- statement: Joy is an American biographical film.
- audit_code: VALID
- notes: Although the attribute_type is tagged as nationality, the statement is grammatical and fact-like. No obvious source artifact.

### Clean 03

- id: `attrv2_0226`
- source_claim_id: `fever_59799:attr1`
- attribute_type: `occupation`
- statement: Lay (entertainer) is a Chinese actor.
- audit_code: VALID
- notes: 

### Clean 04

- id: `attrv2_0260`
- source_claim_id: `fever_191372:attr1`
- attribute_type: `occupation`
- statement: Clark Gable was an actor in It Happened One Night.
- audit_code: VALID
- notes: 

### Clean 05

- id: `attrv2_0275`
- source_claim_id: `fever_162104:attr1`
- attribute_type: `nationality`
- statement: Room 93 is by a singer who is American.
- audit_code: VALID
- notes: Indirect nationality description but still grammatical and factual.

### Clean 06

- id: `attrv2_0294`
- source_claim_id: `fever_196233:attr1`
- attribute_type: `genre`
- statement: The Prince of Egypt is an American animated film.
- audit_code: VALID
- notes: 

### Clean 07

- id: `attrv2_0116`
- source_claim_id: `fever_103736:attr1`
- attribute_type: `nationality`
- statement: The X Factor is a British competition.
- audit_code: VALID
- notes: Slightly coarse category ("competition"), but still a valid attribute statement.

### Clean 08

- id: `attrv2_0065`
- source_claim_id: `fever_200620:attr1`
- attribute_type: `occupation`
- statement: Geoffrey Beevers worked as an actor at the Orange Tree Theatre.
- audit_code: VALID
- notes: 

### Clean 09

- id: `attrv2_0078`
- source_claim_id: `fever_197932:attr1`
- attribute_type: `genre`
- statement: Until Dawn is a horror game.
- audit_code: VALID
- notes: 

### Clean 10

- id: `attrv2_0005`
- source_claim_id: `fever_112969:attr1`
- attribute_type: `nationality`
- statement: Jules Henri Poincare was a French mathematician and theoretical physicist.
- audit_code: VALID
- notes: 

### Clean 11

- id: `attrv2_0019`
- source_claim_id: `fever_2621:attr1`
- attribute_type: `occupation`
- statement: Maria Sharapova is a tennis player.
- audit_code: VALID
- notes: 

### Clean 12

- id: `attrv2_0027`
- source_claim_id: `fever_189072:attr1`
- attribute_type: `nationality`
- statement: Adam West is an American citizen.
- audit_code: VALID
- notes: 

### Clean 13

- id: `attrv2_0234`
- source_claim_id: `fever_54000:attr1`
- attribute_type: `type`
- statement: Derrick Rose is a professional basketball player.
- audit_code: VALID
- notes: attribute_type tag ("type") is somewhat unusual, but the statement itself is a clean occupation/category claim.

### Clean 14

- id: `attrv2_0011`
- source_claim_id: `fever_88611:attr1`
- attribute_type: `nationality`
- statement: Dan Martin is an Irish professional road cyclist.
- audit_code: VALID
- notes: 

### Clean 15

- id: `attrv2_0112`
- source_claim_id: `fever_117362:attr1`
- attribute_type: `occupation`
- statement: Mithun Chakraborty is an actor who has starred in the movie 'Disco Dancer'.
- audit_code: VALID
- notes: 

### Clean 16

- id: `attrv2_0251`
- source_claim_id: `fever_56771:attr1`
- attribute_type: `nationality`
- statement: X-Men: Days of Future Past is an American film.
- audit_code: VALID
- notes: 

### Clean 17

- id: `attrv2_0230`
- source_claim_id: `fever_67989:attr1`
- attribute_type: `occupation`
- statement: Ty Cobb was a baseball player.
- audit_code: VALID
- notes: 

### Clean 18

- id: `attrv2_0263`
- source_claim_id: `fever_206214:attr1`
- attribute_type: `occupation`
- statement: Evan Goldberg is a Canadian director.
- audit_code: VALID
- notes: Interesting because nationality and occupation appear together, but still clean and factual.

### Clean 19

- id: `attrv2_0151`
- source_claim_id: `fever_117955:attr1`
- attribute_type: `nationality`
- statement: Heather Watson is a British citizen.
- audit_code: VALID
- notes: 

### Clean 20

- id: `attrv2_0174`
- source_claim_id: `fever_14703:attr1`
- attribute_type: `occupation`
- statement: Timea Bacsinszky is a tennis player.
- audit_code: VALID
- notes: 

### Clean 21

- id: `attrv2_0286`
- source_claim_id: `fever_190214:attr1`
- attribute_type: `nationality`
- statement: Naruto is a Japanese manga series written and illustrated by Masashi Kishimoto.
- audit_code: VALID
- notes: 

### Clean 22

- id: `attrv2_0155`
- source_claim_id: `fever_57726:attr1`
- attribute_type: `genre`
- statement: The Adjustment Bureau is an American science fiction thriller movie released in 2011.
- audit_code: VALID
- notes: 

### Clean 23

- id: `attrv2_0235`
- source_claim_id: `fever_182158:attr1`
- attribute_type: `nationality`
- statement: Laurie Hernandez is an American gymnast.
- audit_code: VALID
- notes: 

### Clean 24

- id: `attrv2_0114`
- source_claim_id: `fever_101302:attr1`
- attribute_type: `nationality`
- statement: Katie Stevens is an American citizen.
- audit_code: VALID
- notes: 

### Clean 25

- id: `attrv2_0293`
- source_claim_id: `fever_5769:attr1`
- attribute_type: `nationality`
- statement: Adi Shankar is an Indian-born American film director and producer.
- audit_code: VALID
- notes: Slightly more complex dual-nationality phrasing ("Indian-born American"),
but still a legitimate factual attribute statement.

## Corrupted Sample

### Corrupted 01

- id: `attrv2_0572`
- source_claim_id: `fever_161966:attr1`
- attribute_type: `nationality`
- original: Justin Timberlake is an American record producer.
- corrupted: Justin Timberlake is an Indian record producer.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 02

- id: `attrv2_0317`
- source_claim_id: `fever_9872:attr1`
- attribute_type: `genre`
- original: Glee is an American musical comedy-drama series.
- corrupted: Glee is an American horror comedy-drama series.
- replacement: `musical` -> `horror`
- audit_code: VALID
- notes: 

### Corrupted 03

- id: `attrv2_0557`
- source_claim_id: `fever_27654:attr1`
- attribute_type: `occupation`
- original: Philip Seymour Hoffman was an actor in Patch Adams.
- corrupted: Philip Seymour Hoffman was an author in Patch Adams.
- replacement: `actor` -> `author`
- audit_code: VALID
- notes: 

### Corrupted 04

- id: `attrv2_0372`
- source_claim_id: `fever_20235:attr1`
- attribute_type: `genre`
- original: Hotel Transylvania is an American comedy film.
- corrupted: Hotel Transylvania is an American drama film.
- replacement: `comedy` -> `drama`
- audit_code: VALID
- notes: 

### Corrupted 05

- id: `attrv2_0467`
- source_claim_id: `fever_109604:attr1`
- attribute_type: `genre`
- original: Bohemian Rhapsody is a musical composition.
- corrupted: Bohemian Rhapsody is a horror composition.
- replacement: `musical` -> `horror`
- audit_code: ATTRIBUTE_SPACE_MISMATCH
- notes: "musical composition" -> "horror composition"
crosses attribute spaces.
"Horror" is a genre of narrative works, not a natural attribute value for a musical composition.

### Corrupted 06

- id: `attrv2_0389`
- source_claim_id: `fever_32742:attr1`
- attribute_type: `nationality`
- original: Robert Lee Yates is an American.
- corrupted: Robert Lee Yates is an Indian.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 07

- id: `attrv2_0509`
- source_claim_id: `fever_118468:attr1`
- attribute_type: `nationality`
- original: Miranda Kerr was an Australian who modeled for Victoria's Secret.
- corrupted: Miranda Kerr was an American who modeled for Victoria's Secret.
- replacement: `Australian` -> `American`
- audit_code: VALID
- notes: 

### Corrupted 08

- id: `attrv2_0451`
- source_claim_id: `fever_202363:attr1`
- attribute_type: `nationality`
- original: The Illusionist (2006 film) is an American film.
- corrupted: The Illusionist (2006 film) is an Indian film.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 09

- id: `attrv2_0309`
- source_claim_id: `fever_91355:attr1`
- attribute_type: `occupation`
- original: Elizabeth Banks is an American actress.
- corrupted: Elizabeth Banks is an American singer.
- replacement: `actress` -> `singer`
- audit_code: VALID
- notes: 

### Corrupted 10

- id: `attrv2_0404`
- source_claim_id: `fever_223386:attr1`
- attribute_type: `nationality`
- original: Poppy (singer) is an American songwriter.
- corrupted: Poppy (singer) is an Indian songwriter.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 11

- id: `attrv2_0334`
- source_claim_id: `fever_192550:attr1`
- attribute_type: `nationality`
- original: Francois de Belleforest translated the works of Antonio de Guevara and he was French.
- corrupted: Francois de Belleforest translated the works of Antonio de Guevara and he was German.
- replacement: `French` -> `German`
- audit_code: VALID
- notes: 

### Corrupted 12

- id: `attrv2_0526`
- source_claim_id: `fever_23790:attr1`
- attribute_type: `nationality`
- original: Julianne Hough is an American dancer.
- corrupted: Julianne Hough is an Indian dancer.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 13

- id: `attrv2_0374`
- source_claim_id: `fever_130267:attr1`
- attribute_type: `nationality`
- original: Amelia Earhart was an American citizen.
- corrupted: Amelia Earhart was an Indian citizen.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 14

- id: `attrv2_0475`
- source_claim_id: `fever_166761:attr1`
- attribute_type: `occupation`
- original: Billy Wilder was a filmmaker and screenwriter.
- corrupted: Billy Wilder was a musician and screenwriter.
- replacement: `filmmaker` -> `musician`
- audit_code: VALID
- notes: 

### Corrupted 15

- id: `attrv2_0586`
- source_claim_id: `fever_186788:attr1`
- attribute_type: `nationality`
- original: Con Man (web series) is an American web series written by Alan Tudyk.
- corrupted: Con Man (web series) is an Indian web series written by Alan Tudyk.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 16

- id: `attrv2_0408`
- source_claim_id: `fever_110503:attr1`
- attribute_type: `nationality`
- original: Metallica is an American band which one several awards.
- corrupted: Metallica is an Indian band which one several awards.
- replacement: `American` -> `Indian`
- audit_code: TYPO_SOURCE
- notes: Original claim contains a source-quality artifact:
"which one several awards".
Item should not be used regardless of corruption quality.

### Corrupted 17

- id: `attrv2_0335`
- source_claim_id: `fever_133701:attr1`
- attribute_type: `nationality`
- original: The Council on Foreign Relations is an American nonprofit.
- corrupted: The Council on Foreign Relations is an Indian nonprofit.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 18

- id: `attrv2_0449`
- source_claim_id: `fever_39725:attr1`
- attribute_type: `occupation`
- original: Nikolaj Coster-Waldau is an actor known for his role as Jaime Lannister.
- corrupted: Nikolaj Coster-Waldau is an author known for his role as Jaime Lannister.
- replacement: `actor` -> `author`
- audit_code: VALID
- notes: 

### Corrupted 19

- id: `attrv2_0424`
- source_claim_id: `fever_213080:attr1`
- attribute_type: `nationality`
- original: Marlon Brando was in Viva Zapata! and he was American.
- corrupted: Marlon Brando was in Viva Zapata! and he was British.
- replacement: `American` -> `British`
- audit_code: VALID
- notes: 

### Corrupted 20

- id: `attrv2_0564`
- source_claim_id: `fever_170486:attr1`
- attribute_type: `nationality`
- original: Evonne Goolagong Cawley is an Australian.
- corrupted: Evonne Goolagong Cawley is an American.
- replacement: `Australian` -> `American`
- audit_code: VALID
- notes: 

### Corrupted 21

- id: `attrv2_0412`
- source_claim_id: `fever_71258:attr1`
- attribute_type: `genre`
- original: Futurama is an American animated sitcom that was created by Matt Groening.
- corrupted: Futurama is an American documentary sitcom that was created by Matt Groening.
- replacement: `animated` -> `documentary`
- audit_code: VALID
- notes: 

### Corrupted 22

- id: `attrv2_0315`
- source_claim_id: `fever_19025:attr1`
- attribute_type: `nationality`
- original: Home Alone is an American film.
- corrupted: Home Alone is an Indian film.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 23

- id: `attrv2_0415`
- source_claim_id: `fever_228042:attr1`
- attribute_type: `nationality`
- original: Broad Green Pictures is an American film company.
- corrupted: Broad Green Pictures is an Indian film company.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 24

- id: `attrv2_0363`
- source_claim_id: `fever_162873:attr1`
- attribute_type: `nationality`
- original: Broadcast News is an American film.
- corrupted: Broadcast News is an Indian film.
- replacement: `American` -> `Indian`
- audit_code: VALID
- notes: 

### Corrupted 25

- id: `attrv2_0352`
- source_claim_id: `fever_220170:attr1`
- attribute_type: `nationality`
- original: Cate Blanchett is an Australian citizen.
- corrupted: Cate Blanchett is an American citizen.
- replacement: `Australian` -> `American`
- audit_code: VALID
- notes: 
