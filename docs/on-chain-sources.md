# On-chain metrics for the crypto assets — sources survey

Survey of 2026-09-20 for the seven tracked coins (BTC, ETH, SOL, XRP, BNB, ADA, LTC), before
any code. Every endpoint below was called from this machine on that day; the numbers quoted
are what came back. Selection rules: free, no browser, daily granularity, history deep enough to
standardise (a year at least), and a licence that allows a private dashboard.

## TL;DR

- **One primary source covers six of the seven coins with one call: the Coin Metrics
  Community API.** No key, daily, history to 2010, active addresses, transaction counts,
  MVRV, hash rate, issuance, exchange in/out flows (BTC, ETH). Licence CC BY-NC 4.0 (a
  credit line on the dashboard). Rate limit 10 requests per 6 s, far above the one call a
  day we need.
- **Solana is the gap.** Coin Metrics Community has only its price. DefiLlama gives Solana
  daily fees, TVL and stablecoin supply for free; the public RPC gives live throughput; daily
  active addresses need Dune (free tier: 2,500 credits a month, enough for one query a day)
  or a Solscan key.
- **DefiLlama fills the "economic activity" column for all seven chains**: daily fees in USD
  (4–8 years of history), TVL, stablecoin supply on the chain. No key, no stated limit.
- Bitcoin has three extra free sources (mempool.space, Blockchain.com, bitcoin-data.com) for
  hash rate, mempool and the valuation ratios (MVRV-Z, SOPR, NUPL); nice to have, not needed.
- The paid houses (Glassnode, CryptoQuant, Santiment) are not needed: what their free tiers
  allow is a subset of the above with tighter limits.

## 1 · Sources, verified

| Source | Coins | Daily metrics that matter to us | Key | Limits, licence | History | Verdict |
|---|---|---|---|---|---|---|
| **Coin Metrics Community** `community-api.coinmetrics.io/v4` | BTC ETH XRP BNB ADA LTC (SOL: price only) | `AdrActCnt` active addresses, `TxCnt`, `TxTfrCnt` transfers, `CapMVRVCur` MVRV, `AdrBalCnt` addresses with balance, `IssTotUSD` issuance, `BlkCnt`; BTC/ETH/LTC add `HashRate`, `FeeTotNtv`; BTC/ETH add `FlowInExUSD` / `FlowOutExUSD` exchange flows and `SplyExNtv` supply on exchanges | none | 10 req / 6 s per IP; CC BY-NC 4.0, attribution | 2010 for BTC; full for the rest | **primary** |
| **DefiLlama** `api.llama.fi`, `stablecoins.llama.fi` | all seven (chains `bitcoin ethereum solana xrpl bsc cardano litecoin`) | daily chain fees USD (`/overview/fees/<chain>`: 1,680 days for Solana, 3,095 for Ethereum, 522 for XRPL), TVL (`/v2/chains`, `/v2/historicalChainTvl/<chain>`), stablecoin supply on the chain (`/stablecoincharts/<chain>`: Solana 15.7 bn USD, 1,594 days) | none | none stated; free for any use | 1.5–8 years | **secondary, and the Solana fees/TVL source** |
| **Solana public RPC** `api.mainnet-beta.solana.com` | SOL | `getRecentPerformanceSamples`: transactions and non-vote transactions per 60 s sample (≈ 3,900 tx/s, 1,200 non-vote at the time of the call) | none | public endpoint, best effort | live only (we store our own daily average) | **Solana throughput** |
| **Dune API** | SOL (and any chain, by SQL) | daily active addresses, transactions, fees from `solana.transactions` | key | free plan 2,500 credits/month, API included; accounts created before 2026-07-21 became view-only on 2026-09-10 (a fresh account gets the new free plan) | full | **Solana active addresses, if wanted** |
| **Blockchair** `api.blockchair.com/<chain>/stats` | BTC ETH LTC XRP ADA (no SOL, no BNB) | 24-hour snapshot: `transactions_24h`, `blocks_24h`, average and median fee, mempool size, `cdd_24h` coin-days destroyed (BTC, LTC) | none | 1,440 req/day without key | snapshot only (we would store one a day) | backup for tx counts |
| **mempool.space** `mempool.space/api/v1` | BTC | hash rate (922.6 EH/s), difficulty, mempool, fee estimates | none | fair use | full | BTC extra |
| **Blockchain.com charts** `api.blockchain.info/charts/<name>` | BTC | unique addresses used, tx count, hash rate, mempool | none | fair use | 2009 | BTC backup |
| **bitcoin-data.com** (BGeometrics) `bitcoin-data.com/v1/<metric>` | BTC (paid tiers add ETH, SOL, XRP) | active addresses, MVRV-Z, SOPR, NUPL, realised price, hash ribbons | none for the free set | free tier; terms on their portal | full | BTC valuation ratios |
| Glassnode | many | the T1 (free) metrics need an Advanced/Pro plan for the API; 50 calls/day on the light API | key + plan | paid | — | no |
| Santiment | many | free tier through GraphQL, but the last 30 days are cut off on free metrics | key | 1,000 calls/month | — | no: we need today |
| CryptoQuant | BTC ETH mostly | exchange flows, miner data | key + plan | paid for the API | — | no |
| Etherscan / BscScan | ETH, BNB | daily counts are Pro-only; the free key gives gas price and supply | key | 5 req/s | — | not needed given Coin Metrics |
| Blockfrost / Koios | ADA | per-block and per-address data, no daily aggregates | key (Blockfrost) / none (Koios) | 50k req/day | — | not needed given Coin Metrics |
| XRPScan | XRP | ledger stats, accounts | none | fair use | — | not needed given Coin Metrics |

Sample from Coin Metrics for 2026-09-19 (the row is complete at about 02:30 UTC the next day,
`AssetEODCompletionTime`; a 06:00 daily run sees the full day):

| coin | active addresses | transactions | MVRV | exchange inflow USD |
|---|---|---|---|---|
| BTC | 586,590 | 597,042 | 1.53 | 1.13 bn |
| ETH | 698,065 | 1,745,429 | 1.15 | 0.29 bn |
| XRP | 36,291 | 2,380,596 | 0.96 | — |
| LTC | 282,826 | 172,951 | 0.76 | — |
| ADA | 15,109 | 24,314 | 0.62 | — |
| BNB | (available) | (available) | (available) | — |

## 2 · Which metrics, and what they would mean for the index

The index measures the macro narrative and data flow; on-chain data is a different animal
(usage and positioning), so it should enter as its own component with its own sign, the way
the surprise term S and the news term N are separate today. Candidates, in the order of
evidence that they carry information about the next weeks:

| Metric | Coins | Reading | How it would enter |
|---|---|---|---|
| Exchange net flow (`FlowInExUSD − FlowOutExUSD`) | BTC ETH | inflow to exchanges = supply for sale, bearish; outflow = accumulation, bullish | 30-day z-score of the 7-day sum, sign flipped |
| Active addresses | six | usage; a rising 7-day mean against its 90-day mean is bullish | z-score of the 7-day/90-day ratio |
| Transactions and transfers | six (+ SOL non-vote tx/s from RPC) | same as above, noisier (inscriptions, spam) | as above, lower weight |
| Fees paid USD | all seven (DefiLlama) | demand for block space; the only usage metric we have for all seven the same way | z-score of the 7-day/90-day ratio |
| MVRV | six | valuation: > 3 historically overheated, < 1 undervalued; slow | mapped to a bounded −1..1 through the historical distribution, small weight |
| Stablecoin supply on the chain | ETH SOL BNB (DefiLlama) | dry powder on the chain; growth is bullish | 30-day change, z-scored |
| Hash rate | BTC LTC | miner commitment; a fall is bearish (capitulation) | 30-day change, z-scored, BTC and LTC only |
| TVL | ETH SOL BNB | DeFi activity; partly a price echo (TVL is priced in USD) | display only, not in the score |

A first version would take four: exchange net flow (BTC, ETH), active addresses, fees, MVRV.
Each is standardised the way the surprise term already is (`_surprise` in v2 uses the history
it has), so the component starts near zero and grows teeth as history accumulates; Coin Metrics
and DefiLlama both give years of history on the first call, so standardisation works from day
one.

## 3 · How it fits the code

- `chain/` module, one provider per source behind one `ChainProvider.fetch(assets, day)
  -> list[ChainMetric]` Protocol: `coinmetrics.py` (six coins, one request), `defillama.py`
  (fees, stablecoins, TVL; one request per chain), `solana_rpc.py` (throughput). Recorded
  fixtures, like the other providers.
- `chain_metrics` table: `(asset, date, metric)` → `value, source, fetched_at`; an Alembic
  revision. Backfill command `manc chain --since` for the history.
- The daily `manc run` fetches the previous day's metrics after 02:30 UTC (the Coin Metrics
  completion time); `manc fetch` does not touch them (they are daily by nature).
- `ScoringInputs` gains `chain: Mapping[str, tuple[float, ...]]` (metric → history, newest
  last), which v1 and v2 ignore; **formula v3** adds the component `C` with the four metrics
  above and the standardisation rules of section 2; `scale` and `windows` as v2.
- API: `GET /api/v1/assets/{symbol}/chain?from&to`; the asset page gets an "On-chain" panel
  (small multiples, one line per metric, the same 30/90/180/365 range) under the price chart,
  before the formula uses any of it, so the owner can look at the series first.
- Attribution: "On-chain data by Coin Metrics Community (CC BY-NC 4.0) and DefiLlama" in the
  site footer.

Order of work: providers and table with the backfill (one PR), the API and the panel (one
PR), then v3 after two weeks of looking at the panel, as the blueprint did for v2.

## 4 · Open questions for the owner

1. Solana active addresses: Dune (free account, one query a day, an API key in `.env`) or
   leave Solana with fees, TVL, stablecoins and throughput only? Recommendation: leave it for
   now; fees and throughput say most of the same thing.
2. Should the on-chain component go straight into a v3, or stay display-only for a while?
   Recommendation: display first; the formula change is a separate decision once the series
   have been seen.
3. Coin Metrics Community is non-commercial (CC BY-NC). Fine for the private dashboard; if
   manc ever becomes a paid product, it is the one source in the list to replace.
