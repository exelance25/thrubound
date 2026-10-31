# ThruBound demo (LOCAL SIMULATION)

One page that shows the product in ten seconds: set a policy, give an agent permission, let it try
payments, approve or refuse, revoke, and run the independent verifier.

It runs the real ThruBound program code inside a local model of the Thru runtime. **It is not a
Thru network: no signatures, no real tokens, nothing on chain.** It uses only the public
`@thrubound/sdk` API.

```bash
cd thru && bash build_host.sh          # once: builds the simulation library
cd sdk && npm ci && npm run build      # once: builds the SDK
cd ../demo && npm install && npm start # http://127.0.0.1:3100
npm test                               # API smoke test
```

Screenshots: `m2/thrubound-p6/`.
