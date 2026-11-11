# Independent review corrections

The review examined behaviors beyond the initial happy-path fixtures. Regression tests remain in `tests/test_adversarial.py`.

| Finding | Correction | Why it matters |
|---|---|---|
| Decimal arithmetic could round long subcent prices or underflow extreme exponents | Parse bounded plain decimal digits into integer cents; reject exponent/subcent input | Reconciliation must not silently change the invoice amount |
| Adjacent phone numbers could merge into an overlength regex candidate and disappear from detection | Preserve an ambiguous numeric span and deny egress for human review | Incomplete recognition must not quietly approve known ambiguous data |
| Case-distinct external IDs were compared after case folding | Compare already-normalized values exactly and preserve case-sensitive external identity | A convenience normalization must not merge distinct customer records |
| SQLite transaction context did not guarantee connection closure | Use an explicit closing context manager | Predictable local resource lifetime |
| Invalid static paths could close a connection without a response | Reject NUL/backslash and catch path resolution errors | Consistent error behavior for malformed requests |
| Routing distance compared totals for different served jobs | Mark distance comparable only for identical job sets | A cheaper incomplete plan is not a demonstrated efficiency gain |
| UI input could be edited during an in-flight computation | Lock editing during execution and ignore stale project responses | Displayed input and result must describe the same run |

Phone detection is still not comprehensive PII detection. Ambiguous spans can produce false-positive holds. Money parsing supports two-decimal nonnegative amounts only. These are explicit limits, not claims of universal validation.

Browser visual inspection and an external MCP client session were not completed. Live socket tests are included for unrestricted CI; local sandbox restrictions are recorded as skips in verification evidence rather than counted as successful transport checks.
