# manc — prior art and related research

Survey done 2026-09-16, before starting M1. Question: is anyone else building a daily,
per-asset, LLM-tagged macro-news + calendar-surprise score, and what does the literature say
about each piece of the v1 formula (N, S, R)?

## TL;DR

- **No open-source project does the whole thing.** Nothing found combines (a) LLM tagging of
  headlines *per asset with a direction*, (b) a data-surprise term from an economic calendar,
  (c) an event-risk haircut, and (d) a bounded, replayable, versioned formula. Each piece has
  precedents; the combination and the "interpretable index, not a predictor" framing are the
  distinctive parts.
- **The closest things are commercial:** RavenPack (per-entity event sentiment −1..1 with
  relevance and novelty decay, exponentially smoothed into "forex sentiment factors"), LSEG
  MarketPsych (daily sentiment/fear/uncertainty per currency and commodity) and the Citi
  Economic Surprise Index (time-decayed weighted surprises per economy). manc is a small
  open reimplementation of that shape from free sources.
- **The closest academic work** is a 2025 arXiv paper that builds daily news-sentiment
  indices from GDELT headlines with FinBERT and trades EUR/USD, USD/JPY and 10-year futures
  on them; its key finding is that *dispersion* and *volume-weighted impact* mattered more
  than mean sentiment. An SNB working paper (2025) fine-tunes open LLMs on labelled FX news
  and beats FinBERT/lexicons. Lopez-Lira & Tang (2023) is the canonical "headline → direction
  with an LLM" paper.
- **The surprise term has a 25-year literature.** The standard measure is the *standardised
  surprise* (actual − consensus) / σ of past surprises (Balduzzi, Elton & Green 2001), which
  is what Citi and Scotti (2016) aggregate. manc's v1 normaliser (divide by
  max(|consensus|, |previous|)) is a pragmatic stand-in until enough history exists for σ;
  the blueprint already plans the z-score as v2.
- **Known pitfalls to design around:** LLM look-ahead/memorisation when scoring historical
  headlines; verbalised confidence is over-confident and poorly calibrated; ±10% run-to-run
  variance even at temperature 0; model-specific bias (ChatGPT leaned dovish on Fedspeak);
  duplicate stories across feeds inflate N.

## 1 · Projects doing something similar

| Project | News source | Scoring | Per-asset direction? | Calendar / surprise? | Time aggregation | Output | Status |
|---|---|---|---|---|---|---|---|
| [Macro-Sentiment-Agentic-Pipeline](https://github.com/amjad-hanini/Macro-Sentiment-Agentic-Pipeline) | Yahoo Finance RSS, daily cron | FinBERT per headline; "macro themes" via MapReduce; Gemini agents debate | No (market-level) | Uses DJIA/VIX history, not a calendar | Medallion layers into SQLite | Streamlit dashboard, Alpaca paper trades | Hobby; 2 stars, no visible tests |
| [crypto-sentiment-with-llms](https://github.com/Paulescu/crypto-sentiment-with-llms) (Paulescu) | Single headline in | Claude/Ollama → bullish/neutral/bearish + reasoning | Crypto only | No | None | JSON signal | Tutorial-grade, 6 commits |
| [llm-news-sentiment-agent](https://github.com/rkaravangelis/llm-news-sentiment-agent) | Headlines | Ollama qwen3, Pydantic structured output, 5-band score | No | No | None | Score | Early draft |
| [LSEG NewsSentimentWithLLM sample](https://github.com/LSEG-API-Samples/Article.DataLibrary.Python.NewsSentimentWithLLM) | LSEG news API (paid) | GPT classification | No | No | None | Labels | Vendor sample |
| [TradingAgents](https://github.com/tauricresearch/tradingagents) ([paper](https://arxiv.org/abs/2412.20138)) | Data adapters incl. news | Seven LLM roles: fundamentals, sentiment, news, technical analysts, researchers, trader, risk | Per ticker, as free-text debate | News analyst reads "macro indicators" but no surprise math | None; per-decision | Trade decision | Popular research framework, equities |
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (virattt) | Financial datasets API | Investor-persona agents incl. news-sentiment agent | Per ticker | No | None | Signals + reasoning | Very popular, educational, equities |
| [FinRobot](https://arxiv.org/html/2405.14767v1) | Multi-source adapters | Agents write research reports; LLM reasons, code computes | Per ticker | No | None | Report | Platform, equities |
| [Crypto Fear & Greed](https://alternative.me/crypto/) (alternative.me) | Volatility, momentum, social, dominance, trends | Fixed weights (25/25/15/10/10) | BTC only | No | Daily | **0–100 bounded index** | Long-running, widely used |
| [SF Fed Daily News Sentiment Index](https://www.frbsf.org/research-and-insights/data-and-indicators/daily-news-sentiment-index/) | 24 US newspapers via Factiva | Lexicon (Shapiro–Sudhof–Wilson) | No (US economy) | No | Smoothed daily series | Index | Official, updated weekly |
| [Citi Economic Surprise Index](https://en.macromicro.me/charts/45866/global-citi-surprise-index) | Bloomberg consensus vs actual | Weighted std. surprises, 3-month rolling, weights from FX impact, time decay | Per economy | **Yes, only that** | Rolling window with decay | Unbounded index | Commercial, the reference |
| [RavenPack](https://www.ravenpack.com/products/edge/factors/forex-sentiment) | 1000s of feeds | ESS −1..1 per entity per event; relevance 0–100; novelty decay 100,75,56,… | **Yes**, per currency/commodity | Has macro-event taxonomy | Exponential smoothing at several decays | Factors | Commercial |
| [LSEG MarketPsych](https://www.marketpsych.com/ma4/intro) | 2M articles/day | Patented NLP; sentiment, fear, uncertainty, themes per asset | **Yes**, 44 currencies, 53 commodities | No surprise math | 60s / hourly / daily | Scores | Commercial |

Observations:

- The hobby and agentic projects stop at "headline → label" and hand the rest to an LLM
  debate or a trade. None stores inputs to replay under a new formula, and none has a
  deterministic, inspectable aggregation. That is manc's gap to fill.
- The commercial products are the real precedent for N: per-entity direction with relevance
  (≈ confidence), novelty decay and exponential time decay. manc's `cᵢ·wᵢ·λᵢ` is the same
  idea with three scalars.
- Nobody found combines N and S in one number. Citi keeps surprise alone; MarketPsych keeps
  sentiment alone. Practitioners eyeball both. manc's `0.6·N + 0.4·S` is a design choice
  without an external benchmark, which argues for keeping the components visible (already
  planned) and for treating the weights as tunable params (already planned).

## 2 · Research, by formula component

### N — news tagged per asset by an LLM

- **Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?"** (2023, [arXiv](https://arxiv.org/abs/2304.07619), J. Financial Economics 2026). Prompted GPT with headlines for a direction; scores predicted next-day returns, strongest for negative news and small stocks; ability rises with model size; returns decayed as LLM adoption grew. The template for "headline → direction, no fine-tuning".
- **Ballinari & Maly, "FX sentiment analysis with large language models"** (SNB WP 2025-11, [link](https://www.snb.ch/en/publications/research/working-papers/2025/working_paper_2025_11)). Open-source LLMs fine-tuned on labelled FX news beat existing classifiers on accuracy and on trading performance. Closest paper to manc's forex focus; suggests that if a lexical fallback ever becomes the default, quality drops noticeably.
- **Hansen & Kazinnik, "Can ChatGPT Decipher Fedspeak?"** ([NY Fed 2023](https://www.newyorkfed.org/medialibrary/media/research/conference/2023/FinTech/400pm_Hansen_Paper_Kazinnik_2023.pdf)). GPT classifies FOMC sentences on a 5-point dovish→hawkish scale better than BERT and with human-like justifications. Follow-up ([Mantion et al. 2024](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4769112)) found a **systematic dovish bias** in ChatGPT's labels. Relevant because central-bank feeds carry weight 1.0 in manc.
- **Sinha et al., "SEntFiN 1.0"** ([arXiv](https://arxiv.org/abs/2305.12257)). 10,753 headlines with *entity-level* labels; 2,847 headlines carry several entities with **conflicting** sentiment. Supports manc's decision to tag per asset rather than per headline (a hot US CPI is −1 for gold and +1 for USD legs from the same headline).
- **Mavillonio et al., "Measuring Sentiment News with Transformer-Based Language Models"** (2026, [arXiv](https://arxiv.org/abs/2607.13968)). 143k Factiva articles, FinBERT at sentence level, several normalisation schemes to daily; 588 articles rated by 444 humans as the benchmark. Transformers beat lexicons; **the aggregation/normalisation scheme materially changes the index**. Gives a cheap evaluation recipe for manc: hand-rate a sample of tags and measure agreement.
- **"Interpretable ML for Macro Alpha: A News Sentiment Case Study"** (2025, [arXiv](https://arxiv.org/html/2505.16136v1)). GDELT headlines 2015–2025, ≤100/day, FinBERT polarity P(pos)−P(neg). Daily features: mean, **dispersion (std)**, volume, **impact = mean × log(volume)**, Goldstein event score. Assets: EUR/USD, USD/JPY, ZN. SHAP: dispersion and impact were the top features, not mean sentiment. Reported Sharpe > 4 should be read sceptically (headline-only, daily, expanding-window retraining), but the feature finding is cheap to adopt: manc already stores `n_news`; storing the dispersion of `dᵢ·cᵢ` as a component costs nothing.
- **Shapiro, Sudhof & Wilson, "Measuring News Sentiment"** ([SF Fed WP 2017-01](https://www.frbsf.org/economic-research/publications/working-papers/2017/01/), J. Econometrics 2020) and the resulting [Daily News Sentiment Index](https://www.frbsf.org/research-and-insights/data-and-indicators/daily-news-sentiment-index/). Lexicon + negation handling, article scores smoothed into a daily series with sample-composition adjustments. The reference "daily sentiment index from news" in policy circles.
- **Ashwin, Kalamara & Saiz, "Nowcasting Euro Area GDP with News Sentiment"** ([ECB WP 2616](https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp2616~58494f90b7.en.pdf), J. Applied Econometrics 2024, [code](https://github.com/julianashwin/NowcastingEuroNewsJAE)). Daily sentiment from 15 European papers improves euro-area GDP nowcasts, especially in crises. Evidence that news sentiment carries macro signal at daily frequency.
- **Bybee, Kelly, Manela & Xiu, "Business News and Business Cycles"** ([J. Finance 2024](https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13377)). 800k WSJ articles → topic *attention* shares track the macro state and forecast returns. Attention (what the news is about), not just tone, is informative; manc's `category` on calendar events and the per-asset tag counts are a small version of this.
- **RavenPack methodology** ([S&P/RavenPack index method](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-500-rvnpck-ai-sentiment-indices.pdf), [user guide](https://som.ustc.edu.cn/_upload/article/files/c0/28/c4afd94448c68b4ca1c174b1a7c6/e0a62fa2-646e-491a-acc5-18efdbab1181.pdf)). Per-entity event sentiment in −1..1, relevance 0–100 (>75 counts), **novelty decay** so the second, third… story on the same event within 24h gets 75, 56, 42…%, then exponential smoothing at several half-lives. manc dedupes by URL only, so a story carried by Reuters-via-Google, CNBC, MarketWatch and BBC counts four times. Worth a v2 note (title near-duplicate clustering or a novelty weight).

### S — data surprises versus consensus

- **Balduzzi, Elton & Green, "Economic News and Bond Prices"** ([JFQA 2001](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/economic-news-and-bond-prices-evidence-from-the-us-treasury-market/49B6D3645C0D07C21047546615E38F2C)). Introduced the **standardised surprise** `(actual − consensus) / σ(past surprises for that release)`, making CPI, payrolls and PMIs comparable. Markets adjust within a minute; only the surprise moves prices. This is what v1 approximates and v2 should adopt once `calendar_events` holds a few months of `actual`/`consensus`.
- **Andersen, Bollerslev, Diebold & Vega, "Micro Effects of Macro Announcements"** ([AER 2003](https://www.aeaweb.org/articles?id=10.1257/000282803321455151)). FX (DEM, GBP, JPY, CHF, EUR vs USD) jumps on standardised surprises; **bad news moves more than good news**; payrolls, GDP, claims matter most. Grounds the per-category sign map and suggests an asymmetry parameter as a v2 candidate.
- **Scotti, "Surprise and Uncertainty Indexes: Real-time Aggregation of Real-Activity Macro Surprises"** ([Fed IFDP 1093, 2013](https://www.federalreserve.gov/pubs/ifdp/2013/1093/ifdp1093.pdf), J. Monetary Economics 2016). Surprises standardised by their sample σ, weighted by each release's contribution to a dynamic-factor business-conditions index; the weights imply a time decay. Also documents the Citi construction: weighted std. surprises with weights from FX reaction to a 1σ surprise plus a *subjective* decay function. manc's `imp ∈ {0.25, 0.5, 1}` from the calendar's importance flag is the cheap stand-in for those weights.
- **Citi Economic Surprise Index** ([methodology note](https://ia600100.us.archive.org/18/items/citi-economic-surprise-index-methodology-pdf/citi-economic-surprise-index-methodology-pdf.pdf), [explainer](https://globalinvesting.github.io/guide-economic-surprises.html)). Rolling 3 months, recent surprises weighted more. manc's 7-day window is much shorter; that is a deliberate "what just happened" choice, but a longer, decayed S window (like λ for N) is a natural param to expose.

### R — scheduled event risk ahead

- **Lucca & Moench, pre-FOMC drift; Hu, Pan, Wang & Zhu, "Premium for Heightened Uncertainty"** ([JFE 2022](https://www.sciencedirect.com/science/article/abs/pii/S0304405X21004037)); **Ai & Bansal, "Macroeconomic Announcement Premium"** ([NBER](https://www.nber.org/system/files/working_papers/w31923/w31923.pdf)). Uncertainty accumulates before scheduled releases (FOMC, payrolls, ISM, GDP) and resolves on them; a large share of the equity premium is earned around these dates. Supports the premise that scheduled events dominate the near-term risk picture. Note the literature finds a *positive drift* before FOMC, whereas manc uses R only to **shrink conviction toward 50**; that is a different, more conservative use and is fine for an interpretability index, but R should not be read as "expect a fall".

### Composite 0–100 indices

- **Crypto Fear & Greed** ([alternative.me](https://alternative.me/crypto/), [how it works](https://regimerisk.com/blog/alternative-me-crypto-fear-and-greed-index-how-it-works-and-where-it-fails)): fixed-weight blend of five sub-scores into 0–100 with named bands. The same UX pattern as manc's bands (headwind / lean / neutral / tailwind). Its known weaknesses (opaque sub-score normalisation, paused survey component) are the reason to keep manc's components visible and stored.
- **Economic Policy Uncertainty** (Baker, Bloom & Davis): newspaper-count index, unbounded; a reminder that count-based attention measures are a legitimate complement to tone.

### Pitfalls documented in the literature

- **Look-ahead / memorisation.** Lopez-Lira, Tang & Zhu, "The Memorization Problem" (2025); Gao, Jiang & Yan, "Detecting Lookahead Bias in LLM Forecasts" ([arXiv 2512.23847](https://arxiv.org/abs/2512.23847)); "Fake Date Tests" ([arXiv 2601.07992](https://arxiv.org/pdf/2601.07992)); a benchmark at [arXiv 2601.13770](https://arxiv.org/pdf/2601.13770). LLMs recall outcomes for pre-cutoff dates, so backfilling historical headlines with a live model produces contaminated tags. `manc rescore` is safe *because it replays stored tags*; backfilling history through the tagger would not be, and any "does the score predict anything" check must use post-cutoff data only.
- **Confidence is not calibrated.** "On Verbalized Confidence Scores for LLMs" ([arXiv 2412.14737](https://arxiv.org/html/2412.14737v2)): verbalised confidence is generally over-confident and depends heavily on prompt wording; consistency across samples tracks correctness better. The Frontiers 2025 overview of [uncertainty in LLM sentiment analysis](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1609097/full) reports up to 10% accuracy swings across identical runs even with deterministic settings. Implication for `cᵢ`: use it as a coarse weight (e.g. three levels) rather than a precise probability, and don't expect bit-identical tags on re-run.
- **Model-specific bias** (dovish lean in Fedspeak above) and **drift across model versions**: the tag depends on the model string. Storing `model` and prompt version next to each tag makes later comparisons possible; `news_tags` currently stores only `tagged_at`.
- **Signal decay with adoption** (Lopez-Lira & Tang): not a concern for an interpretability index, but another reason not to sell manc as a predictor.

### Adjacent LLM-macro work (context, not design input)

- BIS, [CB-LMs: language models for central banking](https://www.bis.org/publ/work1215.pdf) (WP 1215) and [LLMs: a primer for economists](https://www.bis.org/publ/qtrpdf/r_qt2412b.htm).
- [Can LLMs Take the Pulse of the Economy?](https://arxiv.org/abs/2608.30110v1) (2026): six-month live evaluation of LLM nowcasts of official releases; live, post-cutoff evaluation is the only clean method.
- [Interpreting the Interpreter: post-ECB conference volatility with LLM agents](https://arxiv.org/pdf/2508.13635) (2025).
- [Identifying economic narratives with LLMs](https://arxiv.org/pdf/2506.15041) (2025).
- Surveys: [LLMs in financial investments and market analysis](https://arxiv.org/html/2507.01990v1) (2025); [LLMs for stock forecasting from a hedge-fund perspective](https://arxiv.org/html/2605.05211v1) (2026).

## 3 · What this means for manc

Nothing found argues for changing the blueprint before M1. Concrete, cheap consequences:

1. **Ship v1 as designed.** Its shape (per-asset LLM direction × source weight × exponential decay, plus an importance-weighted surprise term, bounded at 50 ± 50) mirrors what RavenPack/MarketPsych and Citi do commercially, at hobby scale.
2. **Store two more things now, so v2 is a replay, not a refetch:** the tagging `model` (and a prompt version) on `news_tags`, and keep `consensus`/`previous`/`actual` as they are (already planned) so the standardised-surprise σ can be estimated later.
3. **v2 candidates, in order of evidence:** (a) standardised surprise `(actual − consensus)/σ` per release (BEG 2001, Citi, Scotti); (b) novelty weighting for the same story across feeds (RavenPack); (c) expose dispersion of tag directions as a component (Macro Alpha 2025); (d) bad-news asymmetry (ABDV 2003).
4. **Treat `cᵢ` as coarse** and don't promise idempotent tags across runs; the calibration literature is clear.
5. **Evaluation plan that fits "not a predictor":** hand-rate ~100 tags against the LLM (Mavillonio et al. recipe) for agreement; any return-based sanity check only on dates after the model's cutoff (look-ahead literature).
6. **Never backfill history through the LLM tagger** for dates before the model's training cutoff; rescoring stored tags is fine.
