# Fansivibe Product Contract

**"Given face scan input (faceProfileRef from camera), Fansivibe produces a personalized hairstyle recommendation with confidence score and grounded explanation, enabling the user to make a more informed hairstyle decision, which should result in the recommendation being saved to profile."**

| Contract Part | Classification | Reasoning |
|---|---|---|
| Given face scan input | **SUPPORTED** | Camera capture → `faceProfileRef` submission implemented; all 384 Flutter tests pass including client submit/poll/save paths |
| Produces personalized hairstyle recommendation | **SUPPORTED** | Decision engine produces it; 18 unit tests in `test_decision_engine.py` verify all stages; catalog serves 4 looks with reasons |
| Enabling the user to make a more informed hairstyle decision | **HYPOTHESIZED** | Not tested with real users; assumes user reads explanation and uses confidence score to influence decision |
| Which should result in recommendation being saved to profile | **HYPOTHESIZED** | Save mechanism works (TRX-3 all-or-nothing, 9 unit tests verify save+signal commit), but whether user taps save is user behavior not validated |

**Contract boundaries**: The contract does NOT claim Fansivibe directly controls real-world hairstyle outcomes (salon/barber decision is user's). It also does NOT claim user *will* save — only that the mechanism exists and works technically.