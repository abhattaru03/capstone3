# Reflection

I built an orchestrator that sends a question to a SQL agent, a document search agent, or both, and then combines the answers. The SQL agent has a validator that checks the query first.

What worked: the SQL, document, and combined questions gave good answers with sources. The delete question (Q7) got blocked, and the World Cup question (Q8) was refused.

What didn't work: my document index was empty, so I made some fake documents to load. The router only uses keywords, so some SQL questions went to both and used more tokens. Q7 just says "unable to find" instead of saying it was blocked.

Tokens for 10 queries: 2,798 input and 2,214 output.

I didn't finish the Lambda, so there is no response.json or CloudWatch logs. I used the wrong zip file and ran out of time.

Validator tests: I ran 5 tests. 3 passed validation and 2 were blocked. The results are in validator_tests.txt.
