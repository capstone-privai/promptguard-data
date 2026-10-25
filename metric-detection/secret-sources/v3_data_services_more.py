import re
"""Per-service rows for the v3 dataset, grouped by macro category. Each function fills B.ROWS via B.pfx/B.add.

Prefixes, lengths and regexes come from the discovery catalogs (gitleaks, trufflehog, noseyparker, secretlint,
betterleaks, osv-scalibr/Veles, github/docs partner patterns, GitLab secret-detection-rules, microsoft/
security-utilities) and from official vendor SDKs (Toss, PortOne, KIS, Upbit, Naver, Kakao, Solapi, LINE, Lark,
Tencent, Volcengine, Zhipu, DashScope). Values are deterministic fakes from v3_engine.
"""


def _ai(B):
    E = B.E; pfx = B.pfx
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "02"
    pfx(c, "OpenAI_Project_Key", "OpenAI", "secretlint secretlint-rule-openai & gitleaks openai",
        "api.openai.com", "OPENAI_API_KEY", "sk-proj", 74, alph=B64URL, sep="-", sev="Critical", ctx="env",
        regex=r"\bsk-proj-[A-Za-z0-9_-]{40,180}\b",
        what="OpenAI 신형 프로젝트 API 키. `sk-proj-`로 시작하며 길이가 가변(보통 74자 이상)이다. 과금·모델 호출 권한을 가진다.")
    pfx(c, "OpenAI_Service_Account_Key", "OpenAI", "secretlint secretlint-rule-openai",
        "api.openai.com", "OPENAI_API_KEY", "sk-svcacct", 74, alph=B64URL, sep="-", sev="Critical", ctx="py",
        regex=r"\bsk-svcacct-[A-Za-z0-9_-]{40,180}\b",
        what="OpenAI 서비스 계정 키(`sk-svcacct-`). 사람이 아닌 자동화용 계정에 발급되어 서버·CI에서 쓰인다.")
    pfx(c, "OpenAI_Admin_Key", "OpenAI", "secretlint secretlint-rule-openai",
        "api.openai.com/v1/organization", "OPENAI_ADMIN_KEY", "sk-admin", 74, alph=B64URL, sep="-", sev="Critical",
        ctx="env", regex=r"\bsk-admin-[A-Za-z0-9_-]{40,180}\b",
        what="OpenAI 조직 관리 키(`sk-admin-`). 멤버·프로젝트·키 관리 권한을 가져 가장 위험하다.")
    pfx(c, "OpenAI_Legacy_Key", "OpenAI", "gitleaks openai-api-key & noseyparker np.openai",
        "api.openai.com", "OPENAI_API_KEY", "sk", 48, alph=ALNUM, sep="-", sev="Critical", ctx="js",
        regex=r"\bsk-[A-Za-z0-9]{48}\b",
        what="OpenAI 구형 API 키. `sk-` 뒤 48자 영숫자 고정 길이.")
    pfx(c, "Anthropic_API_Key", "Anthropic", "secretlint secretlint-rule-anthropic & gitleaks anthropic-api-key",
        "api.anthropic.com", "ANTHROPIC_API_KEY", "sk-ant-api03", 95, alph=B64URL, sep="-", sev="Critical", ctx="env",
        regex=r"\bsk-ant-api03-[A-Za-z0-9_-]{90,120}\b",
        what="Anthropic(Claude) API 키. `sk-ant-api03-`로 시작하고 끝이 `AA`인 고정 구조.")
    pfx(c, "Anthropic_Admin_Key", "Anthropic", "gitleaks anthropic-admin-api-key",
        "api.anthropic.com", "ANTHROPIC_ADMIN_KEY", "sk-ant-admin01", 93, alph=B64URL, sep="-", sev="Critical",
        ctx="toml", regex=r"\bsk-ant-admin01-[A-Za-z0-9_-]{90,120}\b",
        what="Anthropic 조직 관리 키(`sk-ant-admin01-`). 워크스페이스·키 관리 권한.")
    pfx(c, "Google_Gemini_AI_Studio_Key", "Google", "gitleaks gcp-api-key & GitLab GCP API key & nuclei gcp",
        "generativelanguage.googleapis.com", "GEMINI_API_KEY", "AIza", 35, alph=B64URL, sep="", sev="Critical",
        ctx="js", regex=r"\bAIza[0-9A-Za-z_-]{35}\b",
        what="Google Gemini / AI Studio API 키. GCP 공통 `AIza` 형식(39자)으로 Maps·Firebase 키와 모양이 같다.",
        guide="`AIza` 형식은 Gemini뿐 아니라 Maps·Firebase 등에도 쓰인다. 형식만으로 비밀이지만, 공개 웹용 Maps 키처럼 노출이 전제인 경우와 "
              "서버 비밀 키를 문맥으로 구분하도록 학습한다.")
    pfx(c, "OpenRouter_Key", "OpenRouter", "osv-scalibr veles/openrouter & betterleaks openrouter",
        "openrouter.ai/api", "OPENROUTER_API_KEY", "sk-or-v1", 64, alph=HEX, sep="-", sev="High", ctx="env",
        regex=r"\bsk-or-v1-[0-9a-f]{64}\b", what="OpenRouter 통합 LLM 게이트웨이 키(`sk-or-v1-` + 64 hex).")
    pfx(c, "Moonshot_Kimi_Key", "Moonshot AI", "betterleaks kimi-api-key",
        "api.moonshot.cn", "MOONSHOT_API_KEY", "sk", 48, alph=B64URL, sep="-", sev="High", ctx="py",
        regex=r"(?i)(?:kimi|moonshot)[\w.\-]{0,20}['\"\s:=]{1,5}(sk-[A-Za-z0-9_-]{48})",
        what="Moonshot(Kimi) API 키. `sk-` 48자이며 주변에 kimi/moonshot 키워드가 있다.")
    pfx(c, "DeepSeek_Key", "DeepSeek", "betterleaks deepseek-api-key & trufflehog deepseek",
        "api.deepseek.com", "DEEPSEEK_API_KEY", "sk", 32, alph=HEX, sep="-", sev="High", ctx="env",
        regex=r"(?i)(?:deepseek)[\w.\-]{0,20}['\"\s:=]{1,5}(sk-[a-f0-9]{32})",
        what="DeepSeek API 키. `sk-` 뒤 32자 hex이며 deepseek 키워드가 근처에 있다.")
    pfx(c, "Groq_Key", "Groq", "osv-scalibr veles/grokxaiapikey & secretlint secretlint-rule-groq",
        "api.groq.com", "GROQ_API_KEY", "gsk", 52, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bgsk_[A-Za-z0-9]{52}\b", what="Groq 추론 API 키(`gsk_` + 52자).")
    pfx(c, "xAI_Grok_Key", "xAI", "osv-scalibr veles/grokxaiapikey",
        "api.x.ai", "XAI_API_KEY", "xai", 80, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\bxai-[A-Za-z0-9]{80}\b", what="xAI Grok API 키(`xai-` + 80자).")
    pfx(c, "Perplexity_Key", "Perplexity", "betterleaks perplexity & secrets-patterns-db",
        "api.perplexity.ai", "PERPLEXITY_API_KEY", "pplx", 48, alph=ALNUM, sep="-", sev="High", ctx="js",
        regex=r"\bpplx-[A-Za-z0-9]{48}\b", what="Perplexity API 키(`pplx-` + 48자).")
    pfx(c, "Mistral_Key", "Mistral AI", "trufflehog mistral & betterleaks mistral-api-key",
        "api.mistral.ai", "MISTRAL_API_KEY", "", 32, alph=ALNUM, sep="", sev="High", ctx="py",
        regex=r"(?i)mistral[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9]{32})",
        what="Mistral AI API 키. 접두사 없는 32자 영숫자라 mistral 키워드 문맥으로만 식별된다.",
        neg="your-mistral-api-key-here")
    pfx(c, "Cohere_Key", "Cohere", "trufflehog cohere & secrets-patterns-db",
        "api.cohere.ai", "COHERE_API_KEY", "", 40, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)cohere[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9]{40})",
        what="Cohere API 키. 접두사 없는 40자 영숫자.", neg="<COHERE_API_KEY>")
    pfx(c, "HuggingFace_Token", "Hugging Face", "secretlint secretlint-rule-huggingface & noseyparker",
        "huggingface.co", "HF_TOKEN", "hf", 34, alph=ALNUM, sep="_", sev="High", ctx="export",
        regex=r"\bhf_[A-Za-z0-9]{34}\b", files="~/.cache/huggingface/token, .env",
        what="Hugging Face 액세스 토큰(`hf_` + 34자). 모델·데이터셋 다운로드와 private repo 접근에 쓴다.")
    pfx(c, "Replicate_Token", "Replicate", "trufflehog replicate & secrets-patterns-db",
        "api.replicate.com", "REPLICATE_API_TOKEN", "r8", 40, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\br8_[A-Za-z0-9]{40}\b", what="Replicate 추론 API 토큰(`r8_` + 40자).")
    pfx(c, "TogetherAI_Key", "Together AI", "betterleaks together-ai & secrets-patterns-db",
        "api.together.xyz", "TOGETHER_API_KEY", "", 64, alph=HEX, sep="", sev="High", ctx="py",
        regex=r"(?i)together[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{64})",
        what="Together AI API 키. 64자 hex, 접두사 없음.", neg="${TOGETHER_API_KEY}")
    pfx(c, "Fireworks_Key", "Fireworks AI", "betterleaks fireworks-ai",
        "api.fireworks.ai", "FIREWORKS_API_KEY", "fw", 24, alph=B64URL, sep="_", sev="High", ctx="env",
        regex=r"\bfw_[A-Za-z0-9]{20,30}\b", what="Fireworks AI API 키(`fw_` 접두사).")
    pfx(c, "LangSmith_Key", "LangChain", "betterleaks langsmith & trufflehog langsmith",
        "api.smith.langchain.com", "LANGSMITH_API_KEY", "lsv2_pt", 40, alph=HEX, sep="_", sev="High", ctx="env",
        regex=r"\blsv2_(pt|sk)_[a-f0-9]{32,}\b",
        what="LangSmith(LangChain 관측) API 키. `lsv2_pt_`(개인) / `lsv2_sk_`(서비스) 접두사.")
    pfx(c, "Langfuse_Secret_Key", "Langfuse", "betterleaks langfuse",
        "cloud.langfuse.com", "LANGFUSE_SECRET_KEY", "sk-lf", 36, alph=HEX, sep="-", sev="High", ctx="env",
        regex=r"\bsk-lf-[0-9a-f-]{30,}\b",
        what="Langfuse 비밀 키(`sk-lf-`). 짝인 `pk-lf-`는 공개 키라 비밀이 아니다.",
        guide="`sk-lf-`(비밀)와 `pk-lf-`(공개 퍼블리셔블)를 구분한다. 접두사 두 글자(sk vs pk)가 마스킹 여부를 가른다.")
    pfx(c, "WeightsAndBiases_Key", "Weights & Biases", "trufflehog wandb & secrets-patterns-db",
        "api.wandb.ai", "WANDB_API_KEY", "", 40, alph=HEX, sep="", sev="High", ctx="export",
        regex=r"(?i)wandb[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{40})", files="~/.netrc, .env",
        what="Weights & Biases API 키. 40자 hex이며 `~/.netrc`의 api.wandb.ai 항목에도 저장된다.", neg="${WANDB_API_KEY}")
    pfx(c, "Cursor_Key", "Cursor", "osv-scalibr veles/cursorapikey",
        "api2.cursor.sh", "CURSOR_API_KEY", "key", 64, alph=HEX, sep="_", sev="High", ctx="json",
        regex=r"\bkey_[a-f0-9]{64}\b", files=".cursor/mcp.json, .env",
        what="Cursor 에디터 API 키(`key_` + 64 hex).")
    pfx(c, "Sourcegraph_Cody_Token", "Sourcegraph", "gitleaks sourcegraph-access-token",
        "sourcegraph.com", "SRC_ACCESS_TOKEN", "sgp", 40, alph=HEX, sep="_", sev="High", ctx="env",
        regex=r"\bsgp_[a-f0-9]{16,}_[a-f0-9]{40}\b|\bsgp_[a-f0-9]{40}\b",
        what="Sourcegraph/Cody 액세스 토큰(`sgp_`). 코드 검색·AMP 에이전트 권한.")
    pfx(c, "Apify_Token", "Apify", "trufflehog apify & betterleaks apify",
        "api.apify.com", "APIFY_TOKEN", "apify_api", 36, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bapify_api_[A-Za-z0-9]{36}\b", what="Apify 웹 스크래핑 플랫폼 토큰(`apify_api_`).")
    pfx(c, "Firecrawl_Key", "Firecrawl", "betterleaks firecrawl",
        "api.firecrawl.dev", "FIRECRAWL_API_KEY", "fc", 40, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\bfc-[A-Za-z0-9]{40}\b", what="Firecrawl 크롤링 API 키(`fc-`).")
    pfx(c, "Tavily_Key", "Tavily", "betterleaks tavily",
        "api.tavily.com", "TAVILY_API_KEY", "tvly", 32, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\btvly-[A-Za-z0-9]{32}\b", what="Tavily 검색 API 키(`tvly-`). 에이전트 웹검색 도구에서 흔하다.")
    pfx(c, "SerpApi_Key", "SerpApi", "secrets-patterns-db serpapi",
        "serpapi.com", "SERPAPI_KEY", "", 64, alph=HEX, sep="", sev="Medium", ctx="py",
        regex=r"(?i)serpapi[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{64})",
        what="SerpApi 검색 결과 API 키(64 hex).", neg="YOUR_SERPAPI_KEY")
    pfx(c, "BraveSearch_Key", "Brave", "betterleaks brave-api-key",
        "api.search.brave.com", "BRAVE_API_KEY", "BSA", 27, alph=B64URL, sep="", sev="Medium", ctx="env",
        regex=r"\bBSA[A-Za-z0-9_-]{27}\b", what="Brave Search API 키(`BSA` 접두사).")
    pfx(c, "ElevenLabs_Key", "ElevenLabs", "trufflehog elevenlabs & betterleaks",
        "api.elevenlabs.io", "ELEVENLABS_API_KEY", "sk", 48, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bsk_[A-Za-z0-9]{48}\b", what="ElevenLabs 음성합성 API 키(`sk_` + 48 hex).")
    pfx(c, "Deepgram_Key", "Deepgram", "trufflehog deepgram & secrets-patterns-db",
        "api.deepgram.com", "DEEPGRAM_API_KEY", "", 40, alph=HEX, sep="", sev="High", ctx="header",
        regex=r"(?i)token:?\s+([a-f0-9]{40})", flag="Authorization: Token",
        what="Deepgram 음성인식 API 키(40 hex). `Authorization: Token` 헤더로 보낸다.", neg="<DEEPGRAM_API_KEY>")
    pfx(c, "Pinecone_Key", "Pinecone", "trufflehog pinecone & betterleaks pinecone",
        "*.pinecone.io", "PINECONE_API_KEY", "pcsk", 80, alph=B64URL, sep="_", sev="High", ctx="env",
        regex=r"\bpcsk_[A-Za-z0-9_-]{40,}\b", what="Pinecone 벡터DB API 키(신형 `pcsk_`, 구형은 UUID).")
    pfx(c, "NaverCloud_ClovaStudio_Key", "Naver Cloud", "CLOVA Studio 공식 문서(api.ncloud-docs.com clovastudio)",
        "clovastudio.stream.ntruss.com", "CLOVASTUDIO_API_KEY", "nv", 32, alph=ALNUM, sep="-", sev="High", ctx="header",
        regex=r"\bnv-[A-Za-z0-9]{28,40}\b", flag="Authorization: Bearer",
        what="네이버 CLOVA Studio(HyperCLOVA X) API 키. 신형은 `Bearer nv-...` 형식으로 보낸다.",
        guide="신형 `Bearer nv-` 키와 구형 `X-NCP-CLOVASTUDIO-API-KEY` 헤더 키를 모두 비밀로 본다. 헤더 이름은 지표, 값만 마스킹한다.")
    pfx(c, "Upstage_Key", "Upstage", "betterleaks upstage-api-key",
        "api.upstage.ai", "UPSTAGE_API_KEY", "up", 45, alph=ALNUM, sep="_", sev="High", ctx="py",
        regex=r"(?i)upstage[\w.\-]{0,20}['\"\s:=]{1,5}(up_[A-Za-z0-9]{40,50})",
        what="Upstage(Solar LLM) API 키. OpenAI 호환 클라이언트에 Bearer로 넣어 쓴다.")
    pfx(c, "Zhipu_GLM_Key", "Zhipu AI", "MetaGLM/zhipuai-sdk-python-v4 (_jwt_token.py: apikey.split('.'))",
        "open.bigmodel.cn", "ZHIPUAI_API_KEY", "", 0, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"\b[0-9a-f]{32}\.[A-Za-z0-9]{16}\b",
        what="Zhipu(GLM) API 키. `{id}.{secret}` 형태로 점(.)으로 구분되며, 뒤쪽 secret으로 JWT를 서명한다.",
        neg="your-api-key", var="ZHIPUAI_API_KEY")
    # Zhipu posval override: build id.secret
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "ZHIPUAI_API_KEY=%s.%s\nLOG_LEVEL=info" % (E.tok("", 32, HEX, tag="zhipu1"), E.tok("", 16, ALNUM, tag="zhipu2")),
        "zhipu")
    B.ROWS[-1]["Hard_Negative_Counterpart_Example"] = "# .env.production\nZHIPUAI_API_KEY=your-api-key\nLOG_LEVEL=info"
    pfx(c, "DashScope_Qwen_Key", "Alibaba", "dashscope/dashscope-sdk-python (README: DASHSCOPE_API_KEY=sk-xxx)",
        "dashscope.aliyuncs.com", "DASHSCOPE_API_KEY", "sk", 48, alph=ALNUM, sep="-", sev="High", ctx="export",
        regex=r"\bsk-[A-Za-z0-9]{48}\b", what="Alibaba DashScope(Qwen/통이첸원) API 키(`sk-` 형식).")
    pfx(c, "Baidu_Qianfan_Key", "Baidu", "github/docs baiducloud_api_accesskey & GitLab Baidu",
        "qianfan.baidubce.com", "QIANFAN_ACCESS_KEY", "bce-v3/ALTAK", 35, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\bbce-v3/ALTAK-[A-Za-z0-9]{20,50}\b",
        what="Baidu 千帆(Qianfan) 액세스 키(`bce-v3/ALTAK-` 형식).")
    pfx(c, "VoyageAI_Key", "Voyage AI", "betterleaks voyageai",
        "api.voyageai.com", "VOYAGE_API_KEY", "pa", 43, alph=B64URL, sep="-", sev="Medium", ctx="env",
        regex=r"\bpa-[A-Za-z0-9_-]{43}\b", what="Voyage AI 임베딩 API 키(`pa-`).")
    pfx(c, "Jina_Key", "Jina AI", "betterleaks jina-ai",
        "api.jina.ai", "JINA_API_KEY", "jina", 32, alph=ALNUM, sep="_", sev="Medium", ctx="env",
        regex=r"\bjina_[A-Za-z0-9]{32}\b", what="Jina AI 임베딩/리랭커 API 키(`jina_`).")
    pfx(c, "AssemblyAI_Key", "AssemblyAI", "trufflehog assemblyai",
        "api.assemblyai.com", "ASSEMBLYAI_API_KEY", "", 32, alph=HEX, sep="", sev="Medium", ctx="header",
        regex=r"(?i)authorization:+\s*([a-f0-9]{32})", flag="Authorization",
        what="AssemblyAI 음성인식 키(32 hex). Authorization 헤더에 Bearer 없이 그대로 넣는다.", neg="<ASSEMBLYAI_KEY>")
    pfx(c, "StabilityAI_Key", "Stability AI", "betterleaks stability-ai",
        "api.stability.ai", "STABILITY_API_KEY", "sk", 48, alph=ALNUM, sep="-", sev="Medium", ctx="env",
        regex=r"\bsk-[A-Za-z0-9]{48}\b", what="Stability AI(이미지 생성) API 키(`sk-`).")
    pfx(c, "NVIDIA_NGC_Key", "NVIDIA", "betterleaks nvidia-api-key",
        "integrate.api.nvidia.com", "NVIDIA_API_KEY", "nvapi", 64, alph=B64URL, sep="-", sev="High", ctx="env",
        regex=r"\bnvapi-[A-Za-z0-9_-]{64}\b", what="NVIDIA NGC / NIM API 키(`nvapi-`).")


def _cloud(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "03"
    add(c, "AWS_Access_Key_ID", "awslabs/git-secrets & gitleaks aws-access-token & noseyparker np.aws",
        "AWS IAM 장기 액세스 키 ID. `AKIA`로 시작하는 20자. 짝인 secret key가 있어야 서명되지만 ID도 계정을 특정한다.",
        "AWS API (execute-api, s3 등)", "AWS_ACCESS_KEY_ID, aws_access_key_id",
        r"\b(AKIA|AGPA|AIDA|AROA|ANPA|ANVA)[A-Z0-9]{16}\b",
        "AKIA" + E.d("aws_akia").chars(16, BASE32), "AKIAIOSFODNN7EXAMPLE", "High", ctx="ini",
        var="aws_access_key_id", files="~/.aws/credentials, .env, *.tf",
        guide="`AKIA...`는 계정 식별자에 가깝고 그 자체로도 민감하지만, AWS 공식 문서 예시 `AKIAIOSFODNN7EXAMPLE`는 비밀이 아니다. "
              "접두사가 같아도 `EXAMPLE`로 끝나면 제외한다.")
    add(c, "AWS_Secret_Access_Key", "awslabs/git-secrets & gitleaks aws-secret & SecretBench (AssetHarvester)",
        "AWS 비밀 액세스 키. 40자 base64. 짝인 access key id와 함께 전체 권한을 부여하는 핵심 비밀.",
        "AWS API 전역", "AWS_SECRET_ACCESS_KEY, aws_secret_access_key",
        r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+]{40})['\"]?",
        E.aws_secret("aws_sak"), "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "Critical", ctx="ini",
        var="aws_secret_access_key", files="~/.aws/credentials, .env",
        guide="40자 base64라 엔트로피가 높다. 공식 예시 `wJalrXUtnFEMI/...EXAMPLEKEY`는 비밀이 아니다. access key id와 한 쌍(자산)으로 보되 "
              "마스킹 대상은 secret 쪽이다.")
    add(c, "AWS_Session_Token", "gitleaks & trufflehog aws (STS session token)",
        "AWS STS 임시 세션 토큰. `IQoJ...`로 시작하는 매우 긴 base64. 임시지만 유효 기간 내 전체 권한.",
        "AWS STS", "AWS_SESSION_TOKEN, aws_session_token",
        r"\bIQoJ[A-Za-z0-9/+=]{100,}\b", "IQoJb3JpZ2luX2Vj" + E.d("aws_sts").chars(360, B64),
        "${AWS_SESSION_TOKEN}", "High", ctx="ini", var="aws_session_token",
        guide="수백 자 길이지만 유효 기간이 짧은 임시 토큰이다. 길이만 보지 말고 `IQoJ` 접두사와 session token 문맥으로 식별한다.")
    pfx(c, "AWS_SES_SMTP_Password", "Amazon", "gitleaks & secrets-patterns-db (AWS SES SMTP)",
        "email-smtp.*.amazonaws.com", "SMTP_PASSWORD", "BL", 42, alph=B64, sep="", sev="High", ctx="env",
        regex=r"\bB[A-Za-z0-9/+]{43,}\b",
        what="AWS SES SMTP 비밀번호. IAM secret에서 파생된 44자 base64로, 메일 발송 권한을 가진다.")
    add(c, "GCP_Service_Account_JSON", "gitleaks gcp-service-account & TruffleHog gcp & noseyparker",
        "GCP 서비스 계정 키 JSON 파일. `private_key` 필드에 PEM이 들어 있어 파일 전체가 비밀이다.",
        "*.googleapis.com", "service_account, private_key, client_email",
        r"\"type\":\s*\"service_account\".*\"private_key\":\s*\"-----BEGIN",
        '{\n  "type": "service_account",\n  "project_id": "my-proj",\n  "private_key": "-----BEGIN PRIVATE KEY-----\\n%s\\n-----END PRIVATE KEY-----\\n",\n  "client_email": "svc@my-proj.iam.gserviceaccount.com"\n}'
        % E._pem_body("gcp_sa", 120).replace("\n", "\\n"),
        '{\n  "type": "service_account",\n  "project_id": "my-proj",\n  "private_key": "${GOOGLE_PRIVATE_KEY}",\n  "client_email": "svc@my-proj.iam.gserviceaccount.com"\n}',
        "Critical", ctx="stdout", var="cat", flag="cat sa-key.json", fmt="JSON", channel="File_Read_Tool",
        files="sa-key.json, gcp-credentials.json, GOOGLE_APPLICATION_CREDENTIALS",
        guide="`type: service_account`와 `private_key`의 PEM 본문이 핵심이다. project_id·client_email은 식별자다. `private_key`가 "
              "`${...}` 참조면 비밀이 아니다.")
    pfx(c, "GCP_OAuth_Refresh_Token", "Google", "gitleaks gcp-oauth & nuclei",
        "oauth2.googleapis.com", "GOOGLE_REFRESH_TOKEN", "1//", 50, alph=B64URL, sep="", sev="High", ctx="json",
        regex=r"\b1//[0-9A-Za-z_-]{50,}\b", what="Google OAuth 리프레시 토큰(`1//`로 시작). 장기 재발급 권한.")
    pfx(c, "GCP_OAuth_Client_Secret", "Google", "secretlint secretlint-rule-gcp & GitLab GCP OAuth client secret",
        "oauth2.googleapis.com", "GOOGLE_CLIENT_SECRET", "GOCSPX", 28, alph=B64URL, sep="-", sev="High", ctx="json",
        regex=r"\bGOCSPX-[A-Za-z0-9_-]{28}\b", what="Google OAuth 클라이언트 시크릿(`GOCSPX-`).")
    pfx(c, "Azure_Storage_Account_Key", "Microsoft", "secretlint secretlint-rule-azure & gitleaks azure",
        "*.blob.core.windows.net", "AZURE_STORAGE_KEY", "", 88, alph=B64, sep="", sev="Critical", ctx="env",
        regex=r"(?i)(AccountKey|azure_storage_key)\s*[:=]\s*([A-Za-z0-9/+]{80,120}={0,2})",
        what="Azure 스토리지 계정 키. 88자 base64(끝 `==`). 연결 문자열 `AccountKey=`에도 들어간다.",
        neg="AccountKey=${AZURE_STORAGE_KEY}")
    pfx(c, "Azure_AD_Client_Secret", "Microsoft", "microsoft/security-utilities & gitleaks azure-ad",
        "login.microsoftonline.com", "AZURE_CLIENT_SECRET", "", 40, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\b[A-Za-z0-9._~-]{3}[0-9A-Za-z._~-]{34}[A-Za-z0-9._~-]{3}\b",
        what="Entra ID(Azure AD) 앱 클라이언트 시크릿. 앱 등록에서 발급되며 40자 안팎.", neg="${AZURE_CLIENT_SECRET}")
    pfx(c, "Azure_SAS_Token", "Microsoft", "gitleaks & nuclei (Azure SAS)",
        "*.blob.core.windows.net", "AZURE_SAS", "sig", 43, alph=B64URL, sep="=", sev="High", ctx="env",
        regex=r"(?i)sig=([A-Za-z0-9%/+_-]{40,})", fmt="URL Query",
        what="Azure Shared Access Signature 토큰. URL 쿼리의 `sig=` 값이 서명 비밀이다.")
    pfx(c, "AlibabaCloud_AccessKey_Secret", "Alibaba", "gitleaks alibaba & github/docs alibaba_cloud",
        "*.aliyuncs.com", "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "", 30, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)access[_-]?key[_-]?secret\s*[:=]\s*['\"]?([A-Za-z0-9]{30})",
        what="Alibaba Cloud(阿里云) AccessKey Secret(30자). 짝인 AccessKey ID는 `LTAI`로 시작한다.",
        neg="${ALIBABA_CLOUD_ACCESS_KEY_SECRET}")
    pfx(c, "AlibabaCloud_AccessKey_ID", "Alibaba", "gitleaks alibaba-access-key-id & GitLab",
        "*.aliyuncs.com", "ALIBABA_CLOUD_ACCESS_KEY_ID", "LTAI", 20, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"\bLTAI[A-Za-z0-9]{20}\b", what="Alibaba Cloud AccessKey ID(`LTAI` + 20자). 공개 식별자지만 짝 추적 단서.")
    pfx(c, "TencentCloud_Secret_ID", "Tencent", "GitLab TencentCloudSecretID & github/docs tencent_cloud_secret_id",
        "*.tencentcloudapi.com", "TENCENTCLOUD_SECRET_ID", "AKID", 32, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"\bAKID[0-9A-Za-z]{32}\b", what="Tencent Cloud(腾讯云) SecretId(`AKID` + 32자). 짝인 SecretKey가 비밀이다.")
    pfx(c, "TencentCloud_Secret_Key", "Tencent", "TencentCloud/tencentcloud-sdk-python (credential)",
        "*.tencentcloudapi.com", "TENCENTCLOUD_SECRET_KEY", "", 32, alph=ALNUM, sep="", sev="High", ctx="py",
        regex=r"(?i)secret[_-]?key\s*[:=]\s*['\"]([A-Za-z0-9]{32})['\"]",
        what="Tencent Cloud SecretKey(32자). SDK `credential.Credential(secretId, secretKey)` 두 번째 인자.",
        neg="os.environ['TENCENTCLOUD_SECRET_KEY']")
    pfx(c, "Volcengine_AccessKey_ID", "ByteDance", "GitLab VolcengineAccessKeyID & github/docs volcengine_access_key_id",
        "*.volcengineapi.com", "VOLC_ACCESSKEY", "AKLT", 36, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"\bAKLT[0-9A-Za-z]{30,44}\b", what="Volcengine(火山引擎, ByteDance) Access Key ID(`AKLT`).")
    pfx(c, "Volcengine_Ark_Key", "ByteDance", "github/docs volcengine_ark_api_key",
        "ark.cn-beijing.volces.com", "ARK_API_KEY", "", 0, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        what="Volcengine Ark(豆包/Doubao LLM) API 키. UUID 형식이라 일반 UUID와 문맥으로 구분해야 한다.",
        neg="00000000-0000-0000-0000-000000000000", var="ARK_API_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nARK_API_KEY=%s\nLOG_LEVEL=info" % E.uuid("volc_ark"), "volc_ark")
    pfx(c, "NaverCloud_Access_Key", "Naver Cloud", "github/docs navercloud_pub_access_key & api.ncloud-docs.com",
        "*.apigw.ntruss.com", "NCP_ACCESS_KEY", "ncp_iam_BPASKR", 20, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"\bncp_iam_[A-Za-z0-9]{20,}\b",
        what="네이버 클라우드 플랫폼 Access Key ID. `x-ncp-iam-access-key` 헤더에 들어가며 짝인 Secret Key로 서명한다.")
    pfx(c, "NaverCloud_Secret_Key", "Naver Cloud", "github/docs navercloud_pub_access_key_secret",
        "*.apigw.ntruss.com", "NCP_SECRET_KEY", "", 40, alph=ALNUM, sep="", sev="High", ctx="py",
        regex=r"(?i)secret[_-]?key\s*[:=]\s*['\"]([A-Za-z0-9]{40})['\"]",
        what="네이버 클라우드 Secret Key(40자). `x-ncp-apigw-signature-v2`를 HMAC-SHA256으로 만들 때 쓰는 비밀.",
        neg="${NCP_SECRET_KEY}", var="ncp_secret_key")
    pfx(c, "OracleCloud_Auth_Token", "Oracle", "gitleaks & oci config (OCI auth token)",
        "*.oraclecloud.com", "OCI_AUTH_TOKEN", "", 0, alph=ALNUM, sep="", sev="High", ctx="ini",
        regex=r"(?i)pass_?phrase\s*=\s*(\S+)", files="~/.oci/config, *.pem",
        what="Oracle Cloud(OCI) 설정의 key_file 패스프레이즈/Auth Token. `~/.oci/config`에 fingerprint와 함께 있다.",
        neg="<AUTH_TOKEN>", var="pass_phrase")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "[DEFAULT]\nfingerprint = %s\npass_phrase = %s" % (
            ":".join(E.d("oci_fp").chars(32, HEX)[i:i+2] for i in range(0, 32, 2)),
            E.password("oci_pass", "random")), "oci")
    pfx(c, "DigitalOcean_Token", "DigitalOcean", "osv-scalibr veles/digitaloceanapikey & gitleaks digitalocean-pat",
        "api.digitalocean.com", "DIGITALOCEAN_TOKEN", "dop_v1", 64, alph=HEX, sep="_", sev="High", ctx="env",
        regex=r"\bdop_v1_[a-f0-9]{64}\b", what="DigitalOcean 개인 액세스 토큰(`dop_v1_` + 64 hex).")
    pfx(c, "Linode_Token", "Linode", "gitleaks linode & secrets-patterns-db",
        "api.linode.com", "LINODE_TOKEN", "", 64, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)linode[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{64})",
        what="Linode API 토큰(64 hex).", neg="${LINODE_TOKEN}")
    pfx(c, "IBM_Cloud_IAM_Key", "IBM", "detect-secrets ibm_cloud_iam & gitleaks ibm",
        "iam.cloud.ibm.com", "IBMCLOUD_API_KEY", "", 44, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"(?i)(ibm|cloud)[_-]?api[_-]?key\s*[:=]\s*['\"]?([A-Za-z0-9_-]{44})",
        what="IBM Cloud IAM API 키(44자).", neg="<IBMCLOUD_API_KEY>")
    pfx(c, "Aiven_Token", "Aiven", "betterleaks aiven & secrets-patterns-db",
        "console.aiven.io", "AIVEN_TOKEN", "", 64, alph=B64URL, sep="", sev="Medium", ctx="env",
        regex=r"(?i)aiven[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9/+_-]{40,})",
        what="Aiven 관리형 DB 플랫폼 토큰(긴 base64).", neg="${AIVEN_TOKEN}")
    pfx(c, "Scaleway_Secret_Key", "Scaleway", "gitleaks scaleway & secrets-patterns-db",
        "api.scaleway.com", "SCW_SECRET_KEY", "", 0, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        what="Scaleway Secret Key(UUID 형식). 짝인 Access Key는 `SCW`로 시작.",
        neg="11111111-1111-1111-1111-111111111111", var="SCW_SECRET_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nSCW_SECRET_KEY=%s\nLOG_LEVEL=info" % E.uuid("scw"), "scw")


def _db(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "04"
    for scheme, host, sub in (("postgresql", "db.internal:5432", "PostgreSQL"), ("mysql", "db.internal:3306", "MySQL"),
                              ("mongodb+srv", "cluster0.abcd.mongodb.net", "MongoDB_Atlas"),
                              ("redis", "cache.internal:6379", "Redis"), ("amqp", "mq.internal:5672", "RabbitMQ_AMQP")):
        pw = E.password("dburi:" + sub, "random")
        add(c, f"{sub}_Connection_String", "Skyscanner/whispers uri.py & secretlint database-connection-string & gitleaks",
            f"{sub} 접속 URL. `{scheme}://user:password@host`에서 비밀번호 부분만 비밀이고 host/port/db는 식별자다.",
            host, "DATABASE_URL, user, password",
            rf"{re.escape(scheme)}://[^:/\s]+:([^@/\s]+)@[^\s]+",
            f"{scheme}://svc_user:{pw}@{host}/appdb", f"{scheme}://svc_user:${{DB_PASSWORD}}@{host}/appdb",
            "High", ctx="env", var="DATABASE_URL", fmt="Connection String",
            files=".env, docker-compose.yml, config/database.yml",
            guide=f"URL 전체가 아니라 `user:` 와 `@` 사이 비밀번호만 마스킹한다. `${{DB_PASSWORD}}` 참조나 비밀번호 없는 URL은 제외한다.")
    add(c, "JDBC_Connection_String", "Skyscanner/whispers jproperties & gitleaks (jdbc)",
        "Java JDBC URL. `?user=...&password=...` 쿼리의 password 값이 비밀이다.",
        "jdbc 대상 DB", "jdbc:, password=",
        r"jdbc:[a-z]+://[^?\s]+\?[^\s]*password=([^&\s]+)",
        "jdbc:postgresql://db.internal:5432/app?user=svc&password=" + E.password("jdbc", "random"),
        "jdbc:postgresql://db.internal:5432/app?user=svc&password=${DB_PW}", "High", ctx="java",
        var="spring.datasource.url", fmt="Connection String",
        guide="쿼리스트링의 `password=` 뒤만 비밀이다. user·host·dbname은 식별자이며 `${DB_PW}` 참조는 제외한다.")
    add(c, "ODBC_ADO_NET_Connection_String", "gitleaks & nuclei (odbc/ado.net)",
        "ODBC/ADO.NET 연결 문자열. `Password=...;` 또는 `Pwd=...;` 세미콜론 구분 필드의 비밀번호.",
        "SQL Server/ODBC DSN", "Password=, Pwd=, Server=",
        r"(?i)(password|pwd)\s*=\s*([^;\"']+)[;\"']",
        "Server=sql.internal;Database=app;User Id=sa;Password=" + E.password("odbc", "random") + ";",
        "Server=sql.internal;Database=app;User Id=sa;Password=${SA_PASSWORD};", "High", ctx="stdout",
        var="type", flag="type appsettings.ini", fmt="Connection String", files="web.config, appsettings.json",
        guide="`;`로 구분된 필드 중 Password/Pwd 값만 비밀이다. Server/Database/User Id는 식별자다.")
    pfx(c, "Supabase_Service_Role_JWT", "Supabase", "osv-scalibr veles/supabase & betterleaks supabase",
        "*.supabase.co", "SUPABASE_SERVICE_ROLE_KEY", "", 0, sev="Critical", ctx="env",
        regex=r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        what="Supabase service_role JWT. RLS를 우회하는 관리 키로, 짝인 anon 키(공개)와 역할(role) 클레임으로 구분된다.",
        neg="${SUPABASE_SERVICE_ROLE_KEY}", var="SUPABASE_SERVICE_ROLE_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nSUPABASE_SERVICE_ROLE_KEY=%s\nSUPABASE_URL=https://abcd.supabase.co"
        % E.jwt("supabase_sr", extra={"role": "service_role", "iss": "supabase"}), "supabase_sr")
    B.ROWS[-1]["SLM_Training_Guideline_KR"] = (
        "payload의 `role`이 `service_role`이면 비밀(관리), `anon`이면 공개 키다. 같은 JWT 형식이라도 role 클레임으로 위험도가 갈린다. "
        "anon 키는 클라이언트에 노출되는 설계라 마스킹하면 앱이 깨진다.")
    add(c, "Supabase_Anon_Key_Negative", "osv-scalibr veles/supabase & Supabase 공식 문서",
        "Supabase anon(public) 키. service_role과 형식이 같은 JWT지만 공개 전제라 비밀이 아니다(오탐 방지용 대조군).",
        "*.supabase.co", "SUPABASE_ANON_KEY, role=anon",
        r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]*anon[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\b",
        E.jwt("supabase_anon", extra={"role": "anon", "iss": "supabase"}),
        E.jwt("supabase_anon2", extra={"role": "anon", "iss": "supabase"}),
        "None (Negative)", ctx="js", var="SUPABASE_ANON_KEY", fmt="JWT",
        guide="anon 키는 프런트엔드에 박아 쓰는 공개 키다. JWT 모양이 service_role과 똑같아도 `role:anon`이면 마스킹하지 않는다. "
              "양성/음성 모두 anon이라 모델이 role 클레임만으로 판단하게 한다.")
    pfx(c, "PlanetScale_Password", "PlanetScale", "gitleaks planetscale & betterleaks",
        "*.psdb.cloud", "DATABASE_PASSWORD", "pscale_pw", 43, alph=B64URL, sep="_", sev="High", ctx="env",
        regex=r"\bpscale_pw_[A-Za-z0-9_-]{40,}\b", what="PlanetScale DB 비밀번호 토큰(`pscale_pw_`).")
    pfx(c, "PlanetScale_Service_Token", "PlanetScale", "gitleaks planetscale-token",
        "api.planetscale.com", "PLANETSCALE_TOKEN", "pscale_tkn", 43, alph=B64URL, sep="_", sev="High", ctx="env",
        regex=r"\bpscale_tkn_[A-Za-z0-9_-]{40,}\b", what="PlanetScale 서비스 토큰(`pscale_tkn_`).")
    pfx(c, "Neon_API_Key", "Neon", "betterleaks neon & secrets-patterns-db",
        "console.neon.tech", "NEON_API_KEY", "napi", 48, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bnapi_[A-Za-z0-9]{48}\b", what="Neon 서버리스 Postgres API 키(`napi_`).")
    pfx(c, "Turso_Token", "Turso", "betterleaks turso",
        "*.turso.io", "TURSO_AUTH_TOKEN", "", 0, sev="High", ctx="env",
        regex=r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        what="Turso(libSQL) 인증 토큰(JWT 형식).", neg="${TURSO_AUTH_TOKEN}", var="TURSO_AUTH_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nTURSO_AUTH_TOKEN=%s\nTURSO_DATABASE_URL=libsql://db.turso.io" % E.jwt("turso"), "turso")
    pfx(c, "Upstash_Redis_Token", "Upstash", "betterleaks upstash & secrets-patterns-db",
        "*.upstash.io", "UPSTASH_REDIS_REST_TOKEN", "", 48, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)upstash[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9]{40,})",
        what="Upstash Redis REST 토큰(긴 base64). REST URL과 짝으로 쓰인다.", neg="${UPSTASH_REDIS_REST_TOKEN}")
    pfx(c, "Snowflake_PAT", "Snowflake", "betterleaks snowflake & trufflehog snowflake",
        "*.snowflakecomputing.com", "SNOWFLAKE_TOKEN", "", 0, sev="High", ctx="env",
        regex=r"\bver:[0-9]+-hint:[0-9]+-[A-Za-z0-9/+=]{80,}\b",
        what="Snowflake 프로그래매틱 액세스 토큰(`ver:..-hint:..-` 구조).", neg="${SNOWFLAKE_TOKEN}",
        var="SNOWFLAKE_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nSNOWFLAKE_TOKEN=ver:2-hint:%s-%s\nSNOWFLAKE_ACCOUNT=ab12345.ap-northeast-2.aws"
        % (E.d("sf").chars(8, E.DIGITS), E.d("sf2").chars(96, E.B64)), "snowflake")
    pfx(c, "Databricks_PAT", "Databricks", "secretlint secretlint-rule-databricks & gitleaks databricks",
        "*.cloud.databricks.com", "DATABRICKS_TOKEN", "dapi", 32, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"\bdapi[a-f0-9]{32}(-[0-9])?\b", what="Databricks 개인 액세스 토큰(`dapi` + 32 hex).")
    pfx(c, "Algolia_Admin_Key", "Algolia", "kingfisher fixtures/algolia & trufflehog algolia",
        "*.algolia.net", "ALGOLIA_ADMIN_KEY", "", 32, alph=HEX, sep="", sev="High", ctx="js",
        regex=r"(?i)algolia[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{32})",
        what="Algolia Admin API 키(32 hex). 짝인 Search-Only 키는 공개용이라 비밀이 아니다.",
        neg="process.env.ALGOLIA_ADMIN_KEY",
        guide="Admin 키(쓰기)와 Search-Only 키(공개 검색)는 길이가 같다. 변수명·용도(admin vs search)로 구분해야 한다.")
    pfx(c, "Elastic_Cloud_Key", "Elastic", "osv-scalibr veles/elasticcloudapikey & trufflehog elastic",
        "*.cloud.es.io", "ELASTIC_API_KEY", "", 40, alph=B64, sep="", sev="High", ctx="header",
        regex=r"(?i)ApiKey:?\s+([A-Za-z0-9+/=]{40,})", flag="Authorization: ApiKey", var="ELASTIC_API_KEY",
        what="Elastic Cloud API 키(base64 id:key). `Authorization: ApiKey` 헤더로 보낸다.", neg="${ELASTIC_API_KEY}")
    pfx(c, "Meilisearch_Master_Key", "Meilisearch", "betterleaks meilisearch & secrets-patterns-db",
        "*.meilisearch.io", "MEILI_MASTER_KEY", "", 64, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)meili[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{48,})",
        what="Meilisearch 마스터 키(긴 hex). 모든 인덱스 관리 권한.", neg="<master-key>")
    pfx(c, "Typesense_Key", "Typesense", "secrets-patterns-db typesense",
        "*.typesense.net", "TYPESENSE_API_KEY", "", 32, alph=ALNUM, sep="", sev="Medium", ctx="js",
        regex=r"(?i)typesense[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9]{32})",
        what="Typesense Admin API 키(32자).", neg="${TYPESENSE_API_KEY}")
    pfx(c, "InfluxDB_Token", "InfluxData", "betterleaks influxdb & secrets-patterns-db",
        "*.influxdata.com", "INFLUX_TOKEN", "", 88, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\b[A-Za-z0-9_-]{80,100}\b", what="InfluxDB v2 토큰(88자 base64url).", neg="${INFLUX_TOKEN}")


def _vcs(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "05"
    for p, name, kr in (("ghp", "GitHub_Classic_PAT", "클래식 개인 액세스 토큰"),
                        ("gho", "GitHub_OAuth_Token", "OAuth 앱 액세스 토큰"),
                        ("ghu", "GitHub_User_To_Server", "GitHub App 사용자-서버 토큰"),
                        ("ghs", "GitHub_Server_To_Server", "GitHub App 서버-서버(설치) 토큰"),
                        ("ghr", "GitHub_Refresh_Token", "GitHub App 리프레시 토큰")):
        pfx(c, name, "GitHub", "secretlint secretlint-rule-github & gitleaks github-pat & noseyparker np.github",
            "github.com", "GITHUB_TOKEN", p, 30, alph=ALNUM, sep="_", sev="Critical", checksum=True,
            ctx="yaml", regex=rf"\b{p}_[A-Za-z0-9]{{36}}\b", files="~/.config/gh/hosts.yml, ~/.git-credentials, .env",
            what=f"GitHub {kr}. `{p}_` 뒤 36자이며 마지막 6자는 CRC 체크섬이라 형식 검증을 통과한다.")
    pfx(c, "GitHub_FineGrained_PAT", "GitHub", "secretlint secretlint-rule-github & gitleaks github-fine-grained-pat",
        "github.com", "GITHUB_TOKEN", "github_pat_11", 59, alph=B64URL, sep="", sev="Critical", ctx="env",
        regex=r"\bgithub_pat_[A-Za-z0-9_]{59,86}\b",
        what="GitHub fine-grained PAT(`github_pat_` + 82자). 리포·권한 범위가 지정된 신형 토큰.")
    pfx(c, "GitLab_PAT", "GitLab", "secretlint secretlint-rule-gitlab & gitleaks gitlab-pat",
        "gitlab.com", "GITLAB_TOKEN", "glpat", 20, alph=B64URL, sep="-", sev="Critical", ctx="env",
        regex=r"\bglpat-[A-Za-z0-9_-]{20}\b", what="GitLab 개인 액세스 토큰(`glpat-`).")
    for p, name, kr in (("glptt", "GitLab_Pipeline_Trigger", "파이프라인 트리거 토큰"),
                        ("glrt", "GitLab_Runner_Token", "러너 인증 토큰"),
                        ("gldt", "GitLab_Deploy_Token", "디플로이 토큰"),
                        ("glfeat", "GitLab_Feature_Flag", "피처 플래그 토큰")):
        pfx(c, name, "GitLab", "gitleaks gitlab-* & GitLab secret-detection-rules",
            "gitlab.com", "GITLAB_TOKEN", p, 20, alph=B64URL, sep="-", sev="High", ctx="env",
            regex=rf"\b{p}-[A-Za-z0-9_-]{{20}}\b", what=f"GitLab {kr}(`{p}-`).")
    pfx(c, "Bitbucket_App_Password", "Atlassian", "gitleaks & kingfisher veles/bitbucketcredentials",
        "api.bitbucket.org", "BITBUCKET_APP_PASSWORD", "ATBB", 32, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"\bATBB[A-Za-z0-9]{32,}\b", what="Bitbucket 앱 비밀번호(`ATBB`). git-credentials에 저장된다.")
    pfx(c, "Gitea_Token", "Gitea", "secrets-patterns-db gitea & gitleaks",
        "gitea.internal", "GITEA_TOKEN", "", 40, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)gitea[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{40})", what="Gitea 액세스 토큰(40 hex).",
        neg="${GITEA_TOKEN}")
    pfx(c, "JFrog_Artifactory_Token", "JFrog", "gitleaks jfrog-api-key & secrets-patterns-db",
        "*.jfrog.io", "ARTIFACTORY_TOKEN", "cmVmdGtuOjAx", 64, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\bcmVmdGtuOjAx[A-Za-z0-9]{64,}\b",
        what="JFrog Artifactory 액세스 토큰(`cmVmdGtuOjAx`는 `reftkn:01`의 base64).")
    pfx(c, "NPM_Token", "npm", "secretlint secretlint-rule-npm & gitleaks npm-access-token",
        "registry.npmjs.org", "NPM_TOKEN", "npm", 36, alph=ALNUM, sep="_", sev="High", ctx="stdout",
        regex=r"\bnpm_[A-Za-z0-9]{36}\b", flag="cat ~/.npmrc", channel="File_Read_Tool / Bash_Tool_Stdout",
        files="~/.npmrc, .npmrc, .github/workflows/*.yml", var="//registry.npmjs.org/:_authToken",
        what="npm 자동화 토큰(`npm_` + 36자). `.npmrc`의 `_authToken=`에 저장된다.")
    pfx(c, "PyPI_Token", "PyPI", "gitleaks pypi-upload-token & noseyparker",
        "upload.pypi.org", "PYPI_TOKEN", "pypi-AgEIcHlwaS5vcmc", 70, alph=B64URL, sep="", sev="High", ctx="stdout",
        regex=r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}\b", flag="cat ~/.pypirc",
        channel="File_Read_Tool / Bash_Tool_Stdout", files="~/.pypirc, pyproject.toml, .github/workflows/*.yml",
        what="PyPI 업로드 토큰(`pypi-AgEIcHlwaS5vcmc...`). 패키지 배포 권한.")
    pfx(c, "RubyGems_Key", "RubyGems", "osv-scalibr veles/rubygemsapitoken & gitleaks rubygems-api-token",
        "rubygems.org", "GEM_HOST_API_KEY", "rubygems", 48, alph=HEX, sep="_", sev="High", ctx="env",
        regex=r"\brubygems_[a-f0-9]{48}\b", what="RubyGems API 키(`rubygems_` + 48 hex).")
    pfx(c, "Cargo_Registry_Token", "crates.io", "osv-scalibr veles/cratesioapitoken & gitleaks",
        "crates.io", "CARGO_REGISTRY_TOKEN", "cio", 32, alph=ALNUM, sep="", sev="High", ctx="toml",
        regex=r"\bcio[A-Za-z0-9]{32}\b", files="~/.cargo/credentials.toml",
        what="crates.io(Cargo) API 토큰(`cio` 접두사).")
    pfx(c, "NuGet_Key", "NuGet", "secrets-patterns-db nuget & gitleaks",
        "api.nuget.org", "NUGET_API_KEY", "oy2", 43, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"\boy2[A-Za-z0-9]{43}\b", what="NuGet API 키(`oy2` 접두사).")
    pfx(c, "Packagist_Token", "Packagist", "kingfisher veles/packagistorgupdatetoken",
        "packagist.org", "PACKAGIST_TOKEN", "packagist_uot_", 68, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"\bpackagist_[a-z]{3}_[A-Za-z0-9]{68}\b", what="Packagist(Composer) 업데이트/읽기 토큰.")
    pfx(c, "Hex_Key", "Hex.pm", "secrets-patterns-db hex",
        "hex.pm", "HEX_API_KEY", "", 32, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"(?i)hex[\w.\-]{0,10}['\"\s:=]{1,5}([A-Za-z0-9]{32})", what="Hex.pm(Elixir) API 키(32자).",
        neg="${HEX_API_KEY}")
    add(c, "Jenkins_Credentials_XML", "gitleaks & nuclei (jenkins credentials.xml)",
        "Jenkins credentials.xml의 암호화된 비밀. `{AQAAABAAAA...}` 형태 Base64 블록이지만 마스터 키가 있으면 복호화된다.",
        "Jenkins 컨트롤러", "credentials.xml, apiToken, {AQAAAB",
        r"\{AQAAABAAAA[A-Za-z0-9+/=]{20,}\}",
        "<apiToken>{AQAAABAAAAAg" + E.d("jenkins").chars(44, E.B64) + "=}</apiToken>",
        "<apiToken>{AQAAABAAAAAgEXAMPLEEXAMPLEEXAMPLE=}</apiToken>", "High", ctx="stdout",
        var="cat", flag="cat credentials.xml", fmt="XML", channel="File_Read_Tool",
        files="$JENKINS_HOME/credentials.xml, jobs/*/config.xml",
        guide="`{AQAAAB...}`로 감싼 Base64는 Jenkins가 마스터 키로 암호화한 비밀이다. 복호화 가능하므로 비밀로 본다. `EXAMPLE`이 든 더미는 제외.")
    pfx(c, "CircleCI_PAT", "CircleCI", "gitleaks circleci-access-token & kingfisher veles/circleciproject",
        "circleci.com", "CIRCLECI_TOKEN", "CCIPAT", 40, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bCCIP(AT|RJ)_[A-Za-z0-9]{40,}\b", what="CircleCI 개인/프로젝트 토큰(`CCIPAT_`/`CCIPRJ_`).")
    pfx(c, "Buildkite_Token", "Buildkite", "gitleaks & secrets-patterns-db",
        "api.buildkite.com", "BUILDKITE_API_TOKEN", "bkua", 40, alph=HEX, sep="_", sev="High", ctx="env",
        regex=r"\bbkua_[a-f0-9]{40}\b", what="Buildkite API 액세스 토큰(`bkua_`).")
    pfx(c, "Codecov_Token", "Codecov", "gitleaks codecov & secrets-patterns-db",
        "codecov.io", "CODECOV_TOKEN", "", 0, sev="Medium", ctx="env",
        regex=r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        what="Codecov 업로드 토큰(UUID 형식).", neg="00000000-0000-0000-0000-000000000000", var="CODECOV_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .github/workflows/ci.yml\n      CODECOV_TOKEN: %s" % E.uuid("codecov"), "codecov")
    pfx(c, "Netlify_Token", "Netlify", "betterleaks netlify & secrets-patterns-db",
        "api.netlify.com", "NETLIFY_AUTH_TOKEN", "nf", 36, alph=B64URL, sep="p_", sev="High", ctx="env",
        regex=r"\bnfp_[A-Za-z0-9]{36}\b", what="Netlify 개인 액세스 토큰(`nfp_`).", var="NETLIFY_AUTH_TOKEN")
    pfx(c, "Vercel_Token", "Vercel", "secretlint secretlint-rule-vercel",
        "api.vercel.com", "VERCEL_TOKEN", "vck", 24, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\b(vck|vci|vca|vcp|vcr)_[A-Za-z0-9]{20,60}\b", what="Vercel 액세스 토큰(`vck_`/`vcp_` 등).")
    pfx(c, "Heroku_Platform_Key", "Heroku", "osv-scalibr veles/herokuplatformkey & gitleaks heroku",
        "api.heroku.com", "HEROKU_API_KEY", "HRKU", 36, alph=B64URL, sep="-", sev="High", ctx="env",
        regex=r"\bHRKU-[A-Za-z0-9_-]{36,}\b", what="Heroku 플랫폼 API 키(`HRKU-`).")
    pfx(c, "Render_Key", "Render", "secrets-patterns-db render",
        "api.render.com", "RENDER_API_KEY", "rnd", 48, alph=B64URL, sep="_", sev="High", ctx="env",
        regex=r"\brnd_[A-Za-z0-9_-]{48}\b", what="Render 배포 플랫폼 API 키(`rnd_`).")
    pfx(c, "FlyIO_Token", "Fly.io", "secrets-patterns-db flyio",
        "api.fly.io", "FLY_API_TOKEN", "FlyV1", 100, alph=B64URL, sep=" ", sev="High", ctx="env",
        regex=r"\bFlyV1 [A-Za-z0-9_,=-]{80,}\b", what="Fly.io 배포 토큰(`FlyV1 ` 접두사).")
    pfx(c, "Railway_Token", "Railway", "secrets-patterns-db railway",
        "backboard.railway.app", "RAILWAY_TOKEN", "", 0, sev="High", ctx="env",
        regex=r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        what="Railway 프로젝트 토큰(UUID).", neg="${RAILWAY_TOKEN}", var="RAILWAY_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nRAILWAY_TOKEN=%s" % E.uuid("railway"), "railway")


def _secmgr(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "06"
    pfx(c, "HashiCorp_Vault_Token", "HashiCorp", "secretlint secretlint-rule-hashicorp-vault & gitleaks vault",
        "vault.internal:8200", "VAULT_TOKEN", "hvs", 90, alph=B64URL, sep=".", sev="Critical", ctx="stdout",
        regex=r"\bhvs\.[A-Za-z0-9_-]{90,120}\b", flag="cat ~/.vault-token", channel="File_Read_Tool / Bash_Tool_Stdout",
        files="~/.vault-token, VAULT_TOKEN env", what="HashiCorp Vault 서비스 토큰(`hvs.`). Vault의 모든 시크릿 접근 열쇠.")
    pfx(c, "HashiCorp_Vault_Batch_Token", "HashiCorp", "secretlint secretlint-rule-hashicorp-vault",
        "vault.internal:8200", "VAULT_TOKEN", "hvb", 138, alph=B64URL, sep=".", sev="High", ctx="env",
        regex=r"\bhvb\.[A-Za-z0-9_-]{138,}\b", what="HashiCorp Vault 배치 토큰(`hvb.`).")
    add(c, "Terraform_Cloud_Token", "gitleaks terraform-cloud-api-token",
        "Terraform Cloud API 토큰. `<14자>.atlasv1.<본문>` 구조로 워크스페이스·상태 관리 권한을 가진다.",
        "app.terraform.io", "TFC_TOKEN, credentials.tfrc.json",
        r"\b[A-Za-z0-9]{14}\.atlasv1\.[A-Za-z0-9_-]{60,}\b",
        "%s.atlasv1.%s" % (E.d("tfc1").chars(14, ALNUM), E.d("tfc2").chars(70, B64URL)),
        "${TFC_TOKEN}", "High", ctx="json", var="token", files="~/.terraform.d/credentials.tfrc.json", fmt="JSON",
        guide="`.atlasv1.` 중간 구분자가 핵심 지표다. 앞 14자와 뒤 본문을 합쳐 하나의 토큰이며, `${TFC_TOKEN}` 참조는 제외한다.")
    pfx(c, "Doppler_Token", "Doppler", "gitleaks doppler-api-token & betterleaks",
        "api.doppler.com", "DOPPLER_TOKEN", "dp.pt", 43, alph=ALNUM, sep=".", sev="High", ctx="env",
        regex=r"\bdp\.(pt|st|sa|ct|scim|audit)\.[A-Za-z0-9]{40,}\b", what="Doppler 시크릿 매니저 토큰(`dp.pt.` 등).")
    add(c, "Infisical_Token", "betterleaks infisical & secrets-patterns-db",
        "Infisical 서비스 토큰. `st.<24hex>.<64hex>.<32hex>` 다중 세그먼트 구조.",
        "app.infisical.com", "INFISICAL_TOKEN, st.",
        r"\bst\.[a-f0-9]{24}\.[a-f0-9]{64}\.[a-f0-9]{32}\b",
        "st.%s.%s.%s" % (E.d("inf1").chars(24, HEX), E.d("inf2").chars(64, HEX), E.d("inf3").chars(32, HEX)),
        "${INFISICAL_TOKEN}", "High", ctx="env", var="INFISICAL_TOKEN",
        guide="`st.`로 시작하는 세 개의 hex 세그먼트 전체가 하나의 토큰이다. 점으로 끊겼다고 여러 값으로 보지 말고 한 span으로 묶는다.")
    pfx(c, "Pulumi_Token", "Pulumi", "gitleaks pulumi-api-token & secrets-patterns-db",
        "api.pulumi.com", "PULUMI_ACCESS_TOKEN", "pul", 40, alph=HEX, sep="-", sev="High", ctx="env",
        regex=r"\bpul-[a-f0-9]{40}\b", what="Pulumi IaC 액세스 토큰(`pul-`).")
    pfx(c, "1Password_Service_Token", "1Password", "osv-scalibr veles/onepasswordkeys & betterleaks",
        "my.1password.com", "OP_SERVICE_ACCOUNT_TOKEN", "ops_eyJ", 250, alph=B64URL, sep="", sev="Critical", ctx="env",
        regex=r"\bops_eyJ[A-Za-z0-9_-]{250,}\b", what="1Password 서비스 계정 토큰(`ops_eyJ...`). 볼트 접근 권한.")
    add(c, "SOPS_Age_Private_Key", "gitleaks age-secret-key & FiloSottile/age",
        "SOPS/age 암호화 개인 키. `AGE-SECRET-KEY-1`로 시작하며 이 키로 암호화된 모든 시크릿을 복호화한다.",
        "암호화된 *.enc.yaml 파일", "AGE-SECRET-KEY-1, sops, age",
        r"\bAGE-SECRET-KEY-1[0-9A-Z]{58}\b",
        "AGE-SECRET-KEY-1" + E.d("age").chars(58, "0123456789ABCDEFGHJKMNPQRSTVWXYZ"),
        "AGE-SECRET-KEY-1XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "Critical",
        ctx="stdout", var="cat", flag="cat ~/.config/sops/age/keys.txt", channel="File_Read_Tool",
        files="~/.config/sops/age/keys.txt, keys.txt", fmt="Age Key",
        guide="공개 키 `age1...`(recipient)과 개인 키 `AGE-SECRET-KEY-1...`을 구분한다. 개인 키만 복호화 권한을 가지므로 비밀이다.")
    add(c, "Docker_Config_Auth", "whispers dockercfg.py & gitleaks & nuclei docker-config",
        "~/.docker/config.json의 `auths[*].auth`. base64(user:password)라 레지스트리 자격증명을 담는다.",
        "컨테이너 레지스트리", "auths, auth, .dockerconfigjson",
        r"\"auth\":\s*\"([A-Za-z0-9+/=]{20,})\"",
        '{\n  "auths": {\n    "registry.internal": { "auth": "%s" }\n  }\n}'
        % E.b64url_bytes(b"deployer:" + E.password("docker", "random").encode()).replace("-", "+").replace("_", "/"),
        '{\n  "auths": {\n    "registry.internal": { "auth": "${REGISTRY_AUTH}" }\n  }\n}',
        "High", ctx="stdout", var="cat", flag="cat ~/.docker/config.json", channel="File_Read_Tool",
        files="~/.docker/config.json, .dockerconfigjson secret", fmt="JSON",
        guide="`auth` 값은 base64(user:pass)다. 디코딩 시 자격증명이면 비밀. `${REGISTRY_AUTH}` 참조는 제외한다.")
    add(c, "Kubernetes_Secret_Data", "gitleaks & nuclei & kubectl get secret -o yaml",
        "kubectl이 출력한 Secret 매니페스트. `data` 필드 값들이 base64로 인코딩된 비밀이다.",
        "Kubernetes 클러스터", "kind: Secret, data:, stringData:",
        r"(?s)kind:\s*Secret.*data:\s*\n\s+\S+:\s*[A-Za-z0-9+/=]{8,}",
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: db-creds\ntype: Opaque\ndata:\n  password: %s"
        % E.b64url_bytes(E.password("k8s", "random").encode()).replace("-", "+").replace("_", "/"),
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: db-creds\ntype: Opaque\ndata:\n  password: <base64-encoded>",
        "Critical", ctx="stdout", var="kubectl", flag="kubectl get secret db-creds -o yaml",
        channel="File_Read_Tool / Bash_Tool_Stdout", fmt="YAML / Base64", files="kubectl stdout, *.yaml",
        guide="`kind: Secret`의 `data:` 아래 값은 base64 비밀이다. `stringData:`는 평문이다. 매니페스트 구조(kind/data)와 "
              "값이 실제 인코딩인지 `<base64-encoded>` 플레이스홀더인지로 구분한다.")
    add(c, "Kubernetes_ServiceAccount_JWT", "gitleaks & kubectl (serviceaccount token)",
        "Kubernetes 서비스 계정 토큰. `/var/run/secrets/.../token`의 projected JWT로, API 서버 호출 자격이다.",
        "kube-apiserver", "serviceaccount, kubernetes.io, token",
        r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        E.jwt("k8ssa", extra={"iss": "kubernetes/serviceaccount", "sub": "system:serviceaccount:default:app"}),
        "${SERVICEACCOUNT_TOKEN}", "High", ctx="stdout", var="cat",
        flag="cat /var/run/secrets/kubernetes.io/serviceaccount/token", channel="File_Read_Tool / Bash_Tool_Stdout",
        fmt="JWT", files="/var/run/secrets/kubernetes.io/serviceaccount/token",
        guide="iss가 `kubernetes/serviceaccount`인 JWT는 클러스터 접근 토큰이다. 경로(`/var/run/secrets/...`)와 클레임으로 식별한다.")
    pfx(c, "Harbor_Robot_Token", "Harbor", "secrets-patterns-db harbor",
        "harbor.internal", "HARBOR_ROBOT_SECRET", "", 32, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"(?i)robot[\w.$\-]{0,30}['\"\s:=]{1,5}([A-Za-z0-9]{16,})",
        what="Harbor 레지스트리 로봇 계정 시크릿.", neg="${HARBOR_ROBOT_SECRET}", var="HARBOR_ROBOT_SECRET")


def _enterprise(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "07"
    add(c, "ASPNET_MachineKey", "gitleaks & nuclei (web.config machineKey)",
        "ASP.NET web.config의 machineKey. validationKey/decryptionKey(hex)가 ViewState 위변조를 막는 비밀이다.",
        "ASP.NET 애플리케이션", "machineKey, validationKey, decryptionKey",
        r"(?i)(validation|decryption)Key\s*=\s*\"([A-F0-9]{48,})\"",
        '<machineKey validationKey="%s" decryptionKey="%s" validation="SHA1" />'
        % (E.d("aspval").chars(128, "0123456789ABCDEF"), E.d("aspdec").chars(48, "0123456789ABCDEF")),
        '<machineKey validationKey="AutoGenerate,IsolateApps" decryptionKey="AutoGenerate" />', "High",
        ctx="stdout", var="type", flag="type web.config", fmt="XML", channel="File_Read_Tool",
        files="web.config, machine.config",
        guide="긴 대문자 hex 키가 비밀이다. `AutoGenerate`/`IsolateApps` 지시어는 실제 키가 아니라 자동 생성 설정이므로 마스킹하지 않는다.")
    add(c, "Spring_Jasypt_Password", "gitleaks & WrongSecrets (jasypt) & whispers jproperties",
        "Spring의 Jasypt 암호화 비밀번호. `jasypt.encryptor.password`가 설정값들을 복호화하는 마스터 키다.",
        "Spring Boot 애플리케이션", "jasypt.encryptor.password, ENC(",
        r"(?i)jasypt\.encryptor\.password\s*[:=]\s*(\S+)",
        E.password("jasypt", "random"), "${JASYPT_PASSWORD}", "High", ctx="java",
        var="jasypt.encryptor.password", files="application.properties, application.yml, bootstrap.yml",
        guide="`ENC(...)`로 감싼 값은 이미 암호화된 설정이고, 그것을 푸는 `jasypt.encryptor.password`가 진짜 비밀이다. `${...}` 참조는 제외.")
    add(c, "Django_Secret_Key", "gitleaks django-secret-key & nuclei",
        "Django `SECRET_KEY`. 세션·CSRF·서명에 쓰이는 50자 안팎의 비밀. `django-insecure-`로 시작하면 개발용 자리표시다.",
        "Django 애플리케이션", "SECRET_KEY, django-insecure-",
        r"(?i)SECRET_KEY\s*=\s*['\"]([^'\"]{40,})['\"]",
        "django-" + E.d("django").chars(50, ALNUM + "!@#$%^&*(-_=+)"), "django-insecure-change-me-in-production",
        "High", ctx="py", var="SECRET_KEY", files="settings.py, .env",
        guide="운영용 SECRET_KEY는 비밀이지만, `django-insecure-`로 시작하는 startproject 기본값은 자리표시라 마스킹하지 않는다.")
    add(c, "Rails_Master_Key", "gitleaks rails-master-key & nuclei",
        "Rails `config/master.key`(32 hex). `credentials.yml.enc`를 복호화하는 단일 마스터 키.",
        "Rails 애플리케이션", "master.key, RAILS_MASTER_KEY",
        r"\b[a-f0-9]{32}\b",
        E.d("rails").chars(32, HEX), "<rails-master-key>", "Critical", ctx="stdout", var="cat",
        flag="cat config/master.key", channel="File_Read_Tool", fmt="Raw Hex",
        files="config/master.key, config/credentials.yml.enc",
        guide="변수명 없이 32자 hex만 든 파일(master.key)은 경로가 곧 문맥이다. 같은 32 hex라도 MD5 해시 등과 경로·용도로 구분한다.")
    add(c, "WordPress_Auth_Keys", "gitleaks & WrongSecrets (wp-config salts)",
        "wp-config.php의 AUTH_KEY/SECURE_AUTH_KEY 등 8개 솔트. 쿠키 서명에 쓰이는 긴 랜덤 문자열이다.",
        "WordPress 사이트", "AUTH_KEY, SECURE_AUTH_KEY, NONCE_KEY, define(",
        r"define\(\s*'(AUTH|SECURE_AUTH|LOGGED_IN|NONCE)_(KEY|SALT)'\s*,\s*'([^']{40,})'\s*\)",
        "define('AUTH_KEY', '%s');" % E.d("wpauth").chars(64, ALNUM + "!@#$%^&*()-_ []{}<>~`+=,.;:/?|"),
        "define('AUTH_KEY', 'put your unique phrase here');", "High", ctx="stdout", var="grep",
        flag="grep AUTH_KEY wp-config.php", fmt="PHP", channel="File_Read_Tool", files="wp-config.php",
        guide="실제 생성된 솔트와 설치 기본 문구 `put your unique phrase here`를 구분한다. 후자는 자리표시라 비밀이 아니다.")
    add(c, "Laravel_App_Key", "gitleaks laravel-app-key & nuclei",
        "Laravel `APP_KEY`(`base64:` + 32바이트). 세션·암호화에 쓰는 대칭 키.",
        "Laravel 애플리케이션", "APP_KEY, base64:",
        r"base64:[A-Za-z0-9+/]{43}=",
        "base64:" + E.b64url_bytes(E.d("laravel").raw(32)).replace("-", "+").replace("_", "/") + "=",
        "base64:", "High", ctx="env", var="APP_KEY", files=".env, config/app.php",
        guide="`base64:` 뒤에 44자 본문이 있으면 실제 키다. `php artisan key:generate` 전의 빈 `base64:`는 비밀이 아니다.")
    add(c, "FileZilla_WinSCP_Stored_Password", "gitleaks & SecretBench (sitemanager.xml)",
        "FileZilla sitemanager.xml / WinSCP 세션에 저장된 FTP/SFTP 비밀번호. base64 또는 난독화 저장이다.",
        "FTP/SFTP 서버", "sitemanager.xml, <Pass>, Password=",
        r"<Pass\s+encoding=\"base64\">([A-Za-z0-9+/=]{8,})</Pass>",
        "<Pass encoding=\"base64\">%s</Pass>" % E.b64url_bytes(E.password("filezilla", "random").encode())
        .replace("-", "+").replace("_", "/"),
        "<Pass encoding=\"base64\"></Pass>", "High", ctx="stdout", var="cat", flag="cat sitemanager.xml",
        fmt="XML", channel="File_Read_Tool", files="~/.config/filezilla/sitemanager.xml, WinSCP.ini",
        guide="`<Pass encoding=base64>` 안의 값은 디코딩 가능한 FTP 비밀번호다. 빈 태그나 host/user는 비밀이 아니다.")
    add(c, "Htpasswd_Bcrypt_Line", "whispers htpasswd.py & gitleaks",
        ".htpasswd 한 줄(user:hash). 해시(bcrypt/apr1/sha1)는 평문은 아니지만 오프라인 크래킹 대상이라 민감하다.",
        "Apache/Nginx basic auth", ".htpasswd, $apr1$, $2y$",
        r"^[A-Za-z0-9_.-]+:\$(apr1|2[aby]|6|1)\$[A-Za-z0-9./$]+$",
        "admin:$apr1$%s$%s" % (E.d("htp1").chars(8, ALNUM), E.d("htp2").chars(22, ALNUM + "./")),
        "admin:{PLAIN}changeme", "Medium", ctx="stdout", var="cat", flag="cat .htpasswd",
        fmt="htpasswd", channel="File_Read_Tool", files=".htpasswd, htpasswd",
        guide="`user:$apr1$...` 해시는 민감(Medium)하지만 복호화된 평문은 아니다. 콜론 앞 user는 식별자다. `{PLAIN}` 접두사는 실제 비밀 대조군.")
    pfx(c, "ServiceNow_Token", "ServiceNow", "secrets-patterns-db servicenow",
        "*.service-now.com", "SERVICENOW_TOKEN", "", 32, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"(?i)service[_-]?now[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9]{32})",
        what="ServiceNow OAuth 토큰/비밀번호(32자).", neg="${SERVICENOW_TOKEN}")
    pfx(c, "Zapier_Webhook", "Zapier", "gitleaks & secrets-patterns-db zapier",
        "hooks.zapier.com", "ZAPIER_WEBHOOK", "hooks/catch", 0, sev="Medium", ctx="js",
        regex=r"https://hooks\.zapier\.com/hooks/catch/\d+/[a-z0-9]+/?",
        what="Zapier 캐치 훅 URL. URL 자체가 트리거 비밀이다.", neg="https://hooks.zapier.com/hooks/catch/0/xxxx/",
        var="ZAPIER_WEBHOOK_URL")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        'const url = "https://hooks.zapier.com/hooks/catch/%s/%s/";'
        % (E.d("zap1").chars(7, E.DIGITS), E.d("zap2").chars(8, "abcdefghijklmnopqrstuvwxyz0123456789")), "zapier")


def _fintech(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "08"
    for p, name, kr, sev in (("sk_live", "Stripe_Live_Secret_Key", "라이브 시크릿 키(실결제)", "Critical"),
                             ("sk_test", "Stripe_Test_Secret_Key", "테스트 시크릿 키", "Medium"),
                             ("rk_live", "Stripe_Restricted_Key", "제한 권한 라이브 키", "High"),
                             ("whsec", "Stripe_Webhook_Secret", "웹훅 서명 시크릿", "High")):
        pfx(c, name, "Stripe", "secretlint secretlint-rule-stripe & gitleaks stripe-access-token",
            "api.stripe.com", "STRIPE_SECRET_KEY", p, 24, alph=ALNUM, sep="_", sev=sev, ctx="env",
            regex=rf"\b{p}_[A-Za-z0-9]{{24,99}}\b", what=f"Stripe {kr}. `{p}_` 접두사로 라이브/테스트가 구분된다.",
            guide=f"`{p}_`의 live/test 구분이 위험도를 가른다. 짝인 publishable 키(`pk_`)는 공개용이라 비밀이 아니다. "
                  f"Hard Negative 플레이스홀더와는 본문이 난수인지로 구분한다.")
    add(c, "Stripe_Publishable_Key_Negative", "secretlint secretlint-rule-stripe & Stripe 공식 문서",
        "Stripe publishable 키(`pk_live_`/`pk_test_`). 프런트엔드에 공개되는 설계라 비밀이 아니다(오탐 방지 대조군).",
        "api.stripe.com", "STRIPE_PUBLISHABLE_KEY, pk_live_, pk_test_",
        r"\bpk_(live|test)_[A-Za-z0-9]{24,99}\b", "pk_live_" + E.d("stripe_pk").chars(32, ALNUM),
        "pk_test_" + E.d("stripe_pk2").chars(32, ALNUM), "None (Negative)", ctx="js", var="STRIPE_PUBLISHABLE_KEY",
        guide="`pk_`(publishable)는 공개 키라 마스킹하면 결제 위젯이 깨진다. 접두사 두 글자(sk vs pk)가 비밀 여부를 가른다.")
    pfx(c, "PayPal_Client_Secret", "PayPal", "gitleaks & secrets-patterns-db paypal",
        "api.paypal.com", "PAYPAL_CLIENT_SECRET", "E", 79, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\bE[A-Za-z0-9_-]{79}\b", what="PayPal 클라이언트 시크릿(`E` 시작, 80자).", neg="${PAYPAL_CLIENT_SECRET}")
    pfx(c, "Braintree_Private_Key", "Braintree", "gitleaks braintree & secrets-patterns-db",
        "api.braintreegateway.com", "BT_PRIVATE_KEY", "", 32, alph=HEX, sep="", sev="High", ctx="env", var="braintree_private_key",
        regex=r"(?i)braintree[\w.\-]{0,20}['\"\s:=]{1,5}([a-f0-9]{32})",
        what="Braintree private key(32 hex).", neg="${BRAINTREE_PRIVATE_KEY}")
    pfx(c, "Square_Access_Token", "Square", "osv-scalibr veles/squareapikey & gitleaks square-access-token",
        "connect.squareup.com", "SQUARE_ACCESS_TOKEN", "EAAA", 60, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\bEAAA[A-Za-z0-9_-]{60}\b", what="Square 액세스 토큰(`EAAA` 시작).")
    pfx(c, "Adyen_API_Key", "Adyen", "betterleaks adyen & secrets-patterns-db",
        "*.adyen.com", "ADYEN_API_KEY", "AQE", 0, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\bAQE[A-Za-z0-9]{10,}[A-Za-z0-9+/=]{40,}\b", what="Adyen API 키(`AQE` 시작).",
        neg="${ADYEN_API_KEY}", var="ADYEN_API_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nADYEN_API_KEY=AQE%s\nLOG_LEVEL=info" % E.d("adyen").chars(70, ALNUM), "adyen")
    pfx(c, "Flutterwave_Secret_Key", "Flutterwave", "secrets-patterns-db flutterwave",
        "api.flutterwave.com", "FLW_SECRET_KEY", "FLWSECK_TEST", 12, alph=HEX, sep="-", sev="High", ctx="env",
        regex=r"\bFLWSECK(_TEST)?-[a-f0-9]{12,}\b", what="Flutterwave 시크릿 키(`FLWSECK-`).",
        neg="FLWSECK_TEST-xxxxxxxxxxxx-X")
    pfx(c, "Paystack_Secret_Key", "Paystack", "osv-scalibr veles/paystacksecretkey & gitleaks",
        "api.paystack.co", "PAYSTACK_SECRET_KEY", "sk_live", 32, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bsk_(live|test)_[A-Za-z0-9]{32,}\b", what="Paystack 시크릿 키(`sk_live_`/`sk_test_`).")
    pfx(c, "Shopify_Admin_Token", "Shopify", "secretlint secretlint-rule-shopify & gitleaks shopify-access-token",
        "*.myshopify.com", "SHOPIFY_TOKEN", "shpat", 32, alph=HEX, sep="_", sev="High", ctx="env",
        regex=r"\bshp(at|ca|pa|ss)_[a-fA-F0-9]{32}\b", what="Shopify Admin API 액세스 토큰(`shpat_`).")
    pfx(c, "Plaid_Secret", "Plaid", "gitleaks plaid & secrets-patterns-db",
        "*.plaid.com", "PLAID_SECRET", "", 30, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)plaid[\w.\-]{0,20}secret['\"\s:=]{1,5}([a-f0-9]{30})",
        what="Plaid 금융 데이터 API secret(30 hex). client_id와 짝.", neg="${PLAID_SECRET}")
    # --- Korean PG / brokerage / exchange ---
    for p, name, kr, sev in (("test_sk", "TossPayments_Test_Secret_Key", "테스트 시크릿 키", "Medium"),
                             ("live_sk", "TossPayments_Live_Secret_Key", "라이브 시크릿 키(실결제)", "Critical"),
                             ("test_gsk", "TossPayments_Test_Widget_Secret", "테스트 결제위젯 시크릿", "Medium"),
                             ("live_gsk", "TossPayments_Live_Widget_Secret", "라이브 결제위젯 시크릿", "Critical")):
        pfx(c, name, "Toss Payments", "tosspayments/tosspayments-sample (server.js: Basic base64(secretKey+':'))",
            "api.tosspayments.com", "TOSS_SECRET_KEY", p, 24, alph=ALNUM, sep="_", sev=sev, ctx="js",
            regex=rf"\b{p}_[A-Za-z0-9]{{20,40}}\b", files="server.js, PaymentController.java, .env",
            what=f"토스페이먼츠 {kr}. `{p}_` 접두사로 test/live·API/위젯이 구분된다. `Authorization: Basic base64(시크릿키+':')`로 보낸다.",
            guide=f"토스는 시크릿 키를 ID처럼 써서 `시크릿키:`를 base64로 인코딩해 Basic 헤더에 넣는다. 짝인 클라이언트 키(`{p.replace('sk','ck')}_`)는 "
                  f"공개용이라 비밀이 아니다. test/live 접두사가 위험도를 가른다.")
    add(c, "TossPayments_Client_Key_Negative", "tosspayments/tosspayments-sample",
        "토스페이먼츠 클라이언트 키(`test_ck_`/`live_ck_`). 브라우저 SDK에 넣는 공개 키라 비밀이 아니다(대조군).",
        "js.tosspayments.com", "TOSS_CLIENT_KEY, test_ck_, live_ck_",
        r"\b(test|live)_ck_[A-Za-z0-9]{20,40}\b", "test_ck_" + E.d("toss_ck").chars(24, ALNUM),
        "test_ck_" + E.d("toss_ck2").chars(24, ALNUM), "None (Negative)", ctx="js", var="clientKey",
        guide="클라이언트 키(`_ck_`)는 결제창 호출용 공개 키다. 시크릿 키(`_sk_`/`_gsk_`)와 접두사가 다르며 마스킹하면 결제창이 안 뜬다.")
    add(c, "PortOne_V2_API_Secret", "portone-io/server-sdk (Authorization: PortOne {secret})",
        "포트원(아임포트) V2 API 시크릿. `Authorization: PortOne {secret}` 헤더로 서버에서만 쓴다.",
        "api.portone.io", "PORTONE_API_SECRET, Authorization: PortOne",
        r"(?i)PortOne\s+([A-Za-z0-9]{40,})", E.d("portone").chars(64, ALNUM), "PortOne ${PORTONE_API_SECRET}",
        "Critical", ctx="curl", var="PORTONE_API_SECRET", flag="Authorization: PortOne",
        rhost="https://api.portone.io/payments", files="server SDK, .env",
        guide="`PortOne ` 뒤 긴 토큰만 비밀이다. 짝인 `storeId`(store-UUID)와 `channelKey`(channel-key-UUID)는 공개 식별자라 비밀이 아니다.")
    add(c, "PortOne_Webhook_Secret", "portone-io/server-sdk (webhook.py: _prefix='whsec_')",
        "포트원 웹훅 시크릿(`whsec_`). 웹훅 본문 서명 검증에 쓰는 비밀로, Svix 호환 형식이다.",
        "포트원 웹훅 수신 서버", "PORTONE_WEBHOOK_SECRET, whsec_",
        r"\bwhsec_[A-Za-z0-9+/=]{32,}\b", "whsec_" + E.d("po_wh").chars(40, ALNUM),
        "whsec_${WEBHOOK_SECRET}", "High", ctx="env", var="PORTONE_WEBHOOK_SECRET",
        guide="`whsec_` 웹훅 서명 키는 Stripe/Svix와 같은 접두사를 쓴다. storeId·paymentId 같은 식별자와 구분한다.")
    add(c, "KIS_AppKey_AppSecret", "koreainvestment/open-trading-api (kis_devlp.yaml, kis_auth.py)",
        "한국투자증권 KIS Open API 앱키/앱시크릿. appsecret으로 `/oauth2/tokenP`에서 접근토큰을 발급해 계좌·주문 권한을 얻는다.",
        "openapi.koreainvestment.com:9443", "KIS_APP_KEY, KIS_APP_SECRET, appsecret",
        r"(?i)(app_?secret|my_sec)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{140,200})",
        '# kis_devlp.yaml\nmy_app: "PS%s"\nmy_sec: "%s"' % (E.d("kis_app").chars(34, ALNUM),
        E.d("kis_sec").chars(180, ALNUM + "/+=")),
        '# kis_devlp.yaml\nmy_app: "앱키"\nmy_sec: "앱키 시크릿"', "Critical", ctx="raw", var="KIS_APP_SECRET", fmt="YAML",
        files="kis_devlp.yaml, ~/KIS/config/kis_devlp.yaml, claude_desktop_config.json",
        guide="appkey(공개 식별자)와 appsecret(180자 안팎 비밀)을 구분한다. `앱키 시크릿` 같은 한국어 자리표시 기본값은 비밀이 아니다. "
              "발급된 access_token(1일 유효)도 비밀이다.")
    add(c, "Upbit_Open_API_Secret_Key", "sharebook-kr/pyupbit (exchange_api.py: jwt.encode(payload, secret))",
        "업비트 Open API Secret Key. access key와 함께 JWT를 HS256으로 서명해 `Authorization: Bearer`로 주문 권한을 얻는다.",
        "api.upbit.com", "UPBIT_SECRET_KEY, access_key, query_hash",
        r"(?i)secret[\w]*\s*[:=]\s*['\"]([A-Za-z0-9]{40})['\"]",
        E.d("upbit_sec").chars(40, ALNUM), "본인 값으로 변경", "Critical",
        ctx="py", var="secret", files="config.py, .env", fmt="Source Code",
        guide="access key(식별자)와 secret key(서명 비밀)를 구분한다. secret으로 JWT를 서명하므로 노출 시 주문·출금이 가능하다. "
              "`본인 값으로 변경` 같은 한국어 자리표시는 비밀이 아니다.")
    pfx(c, "Binance_API_Secret", "Binance", "gitleaks binance & secrets-patterns-db",
        "api.binance.com", "BINANCE_API_SECRET", "", 64, alph=ALNUM, sep="", sev="Critical", ctx="env",
        regex=r"(?i)binance[\w.\-]{0,20}secret['\"\s:=]{1,5}([A-Za-z0-9]{64})",
        what="Binance API Secret(64자). HMAC 서명으로 거래 권한.", neg="${BINANCE_API_SECRET}")
    pfx(c, "Coinbase_CDP_Key", "Coinbase", "gitleaks coinbase & betterleaks",
        "api.coinbase.com", "COINBASE_API_SECRET", "", 0, sev="Critical", ctx="env",
        regex=r"-----BEGIN EC PRIVATE KEY-----", what="Coinbase CDP(Developer Platform) API 키. EC private key 포함.",
        neg="${COINBASE_API_SECRET}", var="COINBASE_API_SECRET")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        'COINBASE_API_SECRET="-----BEGIN EC PRIVATE KEY-----\\n%s\\n-----END EC PRIVATE KEY-----\\n"'
        % E._pem_body("coinbase", 118).replace("\n", "\\n"), "coinbase")
    pfx(c, "Polygon_IO_Key", "Polygon.io", "secrets-patterns-db polygon",
        "api.polygon.io", "POLYGON_API_KEY", "", 32, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"(?i)polygon[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9_]{32})",
        what="Polygon.io 시세 데이터 API 키(32자).", neg="${POLYGON_API_KEY}")
    pfx(c, "Alpaca_Key", "Alpaca", "secrets-patterns-db alpaca & gitleaks",
        "api.alpaca.markets", "APCA_API_SECRET_KEY", "", 40, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)APCA[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9/+]{40})",
        what="Alpaca 증권 API secret key(40자). 짝인 key id는 `PK`/`AK`로 시작.", neg="${APCA_API_SECRET_KEY}")


def _messaging(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "09"
    pfx(c, "Slack_Bot_Token", "Slack", "secretlint secretlint-rule-slack & gitleaks slack-bot-token & noseyparker",
        "slack.com/api", "SLACK_BOT_TOKEN", "xoxb", 24, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\bxoxb-\d{10,13}-\d{10,13}-[A-Za-z0-9]{24}\b", var="SLACK_BOT_TOKEN",
        what="Slack 봇 토큰(`xoxb-`). 워크스페이스 봇 권한.")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nSLACK_BOT_TOKEN=xoxb-%s-%s-%s\nLOG_LEVEL=info"
        % (E.d("slb1").chars(12, DIGITS), E.d("slb2").chars(12, DIGITS), E.d("slb3").chars(24, ALNUM)), "slackbot")
    pfx(c, "Slack_User_Token", "Slack", "secretlint secretlint-rule-slack & gitleaks slack-user-token",
        "slack.com/api", "SLACK_USER_TOKEN", "xoxp", 24, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\bxoxp-[0-9A-Za-z-]{40,}\b", var="SLACK_USER_TOKEN", what="Slack 사용자 토큰(`xoxp-`).")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "SLACK_USER_TOKEN=xoxp-%s-%s-%s-%s" % (E.d("slp1").chars(12, DIGITS), E.d("slp2").chars(12, DIGITS),
        E.d("slp3").chars(12, DIGITS), E.d("slp4").chars(32, HEX)), "slackuser")
    pfx(c, "Slack_App_Level_Token", "Slack", "osv-scalibr veles/slackappleveltoken & gitleaks slack-app-token",
        "slack.com/api", "SLACK_APP_TOKEN", "xapp", 0, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\bxapp-\d-[A-Z0-9]+-\d+-[a-f0-9]+\b", var="SLACK_APP_TOKEN", what="Slack 앱 레벨 토큰(`xapp-`).",
        neg="${SLACK_APP_TOKEN}")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "SLACK_APP_TOKEN=xapp-1-%s-%s-%s" % (E.d("sla1").chars(11, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        E.d("sla2").chars(13, DIGITS), E.d("sla3").chars(64, HEX)), "slackapp")
    add(c, "Slack_Incoming_Webhook", "secretlint secretlint-rule-slack & gitleaks slack-webhook-url & noseyparker",
        "Slack 수신 웹훅 URL. URL 경로의 토큰 세그먼트가 비밀이라, URL을 아는 사람은 누구나 메시지를 보낼 수 있다.",
        "hooks.slack.com", "SLACK_WEBHOOK_URL, hooks.slack.com/services",
        r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]{24}",
        "https://hooks.slack.com/services/T%s/B%s/%s" % (E.d("slw1").chars(10, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        E.d("slw2").chars(10, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), E.d("slw3").chars(24, ALNUM)),
        "https://hooks.slack.com/services/$SLACK_WORKSPACE/$SLACK_CHANNEL/<WEBHOOK_TOKEN>", "High", ctx="js",
        var="SLACK_WEBHOOK_URL", fmt="URL",
        guide="URL 전체가 비밀이다. 특히 마지막 24자 세그먼트가 핵심이고, `<WEBHOOK_TOKEN>`·`$VAR` 참조로 채운 예시 URL은 제외한다.")
    add(c, "Discord_Bot_Token", "secrets-patterns-db discord & gitleaks discord-api-token & noseyparker",
        "Discord 봇 토큰. `base64(userid).timestamp.hmac` 3세그먼트 구조로 봇 전체 권한을 가진다.",
        "discord.com/api", "DISCORD_BOT_TOKEN, Bot ",
        r"\b[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,38}\b",
        "%s.%s.%s" % (E.d("disc1").chars(24, B64URL), E.d("disc2").chars(6, B64URL), E.d("disc3").chars(38, B64URL)),
        "Bot ${DISCORD_TOKEN}", "High", ctx="env", var="DISCORD_BOT_TOKEN",
        guide="점으로 끊긴 세 세그먼트가 하나의 토큰이다. 첫 글자는 보통 M/N/O다. `Bot ${...}` 참조는 제외한다.")
    pfx(c, "Telegram_Bot_Token", "Telegram", "osv-scalibr veles/telegrambotapitoken & gitleaks telegram-bot-api-token",
        "api.telegram.org", "TELEGRAM_BOT_TOKEN", "", 35, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b", var="TELEGRAM_BOT_TOKEN",
        what="Telegram 봇 토큰(`<bot_id>:<35자>`). 콜론 앞 숫자는 공개 봇 id, 뒤가 비밀.", neg="123456789:${BOT_SECRET}")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nTELEGRAM_BOT_TOKEN=%s:%s\nLOG_LEVEL=info"
        % (E.d("tg1").chars(9, DIGITS), E.d("tg2").chars(35, B64URL)), "telegram")
    pfx(c, "Mattermost_Token", "Mattermost", "gitleaks mattermost-access-token & secrets-patterns-db",
        "*.mattermost.com", "MM_TOKEN", "", 26, alph="abcdefghijklmnopqrstuvwxyz0123456789", sep="", sev="High",
        ctx="env", regex=r"(?i)mattermost[\w.\-]{0,20}['\"\s:=]{1,5}([a-z0-9]{26})",
        what="Mattermost 액세스 토큰(26자).", neg="${MATTERMOST_TOKEN}", var="MATTERMOST_TOKEN")
    add(c, "LINE_Channel_Access_Token", "line/line-bot-sdk-python (Configuration(access_token=...))",
        "LINE Messaging API 채널 액세스 토큰. 매우 긴 base64 JWT 유사 문자열로, 메시지 발송 권한.",
        "api.line.me", "LINE_CHANNEL_ACCESS_TOKEN, channel_access_token",
        r"(?i)channel[_-]?access[_-]?token['\"\s:=]{1,5}([A-Za-z0-9+/=]{150,})",
        "channel_access_token=" + E.d("line_at").chars(170, ALNUM + "+/="),
        "channel_access_token=YOUR_CHANNEL_ACCESS_TOKEN", "High", ctx="env", var="LINE_CHANNEL_ACCESS_TOKEN",
        guide="LINE는 채널 액세스 토큰(발송 비밀, 매우 김)과 채널 시크릿(서명 검증용 32 hex)을 둘 다 쓴다. 각각 다른 행으로 학습한다.")
    pfx(c, "LINE_Channel_Secret", "LINE", "line/line-bot-sdk-python (WebhookHandler(channel_secret))",
        "api.line.me", "LINE_CHANNEL_SECRET", "", 32, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)channel[_-]?secret['\"\s:=]{1,5}([a-f0-9]{32})", var="LINE_CHANNEL_SECRET",
        what="LINE 채널 시크릿(32 hex). 웹훅 서명(X-Line-Signature) 검증에 쓴다.", neg="${LINE_CHANNEL_SECRET}")
    add(c, "Twilio_Account_SID_Auth_Token", "detect-secrets twilio & gitleaks twilio-api-key & TruffleHog twilio",
        "Twilio Account SID(`AC`+32hex, 공개 식별자)와 Auth Token(32 hex, 비밀)의 쌍. Auth Token만 마스킹 대상.",
        "api.twilio.com", "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, AC",
        r"(?i)auth[_-]?token\s*[:=]\s*['\"]?([a-f0-9]{32})",
        "TWILIO_ACCOUNT_SID=AC%s\nTWILIO_AUTH_TOKEN=%s" % (E.d("tw1").chars(32, HEX), E.d("tw2").chars(32, HEX)),
        "TWILIO_ACCOUNT_SID=AC%s\nTWILIO_AUTH_TOKEN=${AUTH_TOKEN}" % E.d("tw3").chars(32, HEX),
        "High", ctx="env", var="TWILIO", fmt="Key-Value Assignment",
        guide="`AC`로 시작하는 SID는 공개 계정 식별자다. 같은 32 hex라도 Auth Token만 비밀이다(AssetHarvester식 쌍 문맥).")
    pfx(c, "SendGrid_Key", "SendGrid", "secretlint secretlint-rule-sendgrid & gitleaks sendgrid-api-token & noseyparker",
        "api.sendgrid.com", "SENDGRID_API_KEY", "SG", 66, alph=B64URL, sep=".", sev="High", ctx="env",
        regex=r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b", var="SENDGRID_API_KEY",
        what="SendGrid API 키(`SG.` + 두 세그먼트). 메일 발송 권한.", neg="SG.${SENDGRID_KEY}")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "SENDGRID_API_KEY=SG.%s.%s" % (E.d("sg1").chars(22, B64URL), E.d("sg2").chars(43, B64URL)), "sendgrid")
    pfx(c, "Mailgun_Key", "Mailgun", "gitleaks mailgun-private-api-token & secrets-patterns-db",
        "api.mailgun.net", "MAILGUN_API_KEY", "key", 32, alph=HEX, sep="-", sev="High", ctx="env",
        regex=r"\bkey-[a-f0-9]{32}\b", what="Mailgun private API 키(`key-` + 32 hex).")
    pfx(c, "Mailchimp_Key", "Mailchimp", "gitleaks mailchimp-api-key & secrets-patterns-db",
        "*.api.mailchimp.com", "MAILCHIMP_API_KEY", "", 32, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"\b[a-f0-9]{32}-us\d{1,2}\b", what="Mailchimp API 키(`<32hex>-us<N>`, 끝에 데이터센터).",
        neg="${MAILCHIMP_API_KEY}-us1", var="MAILCHIMP_API_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nMAILCHIMP_API_KEY=%s-us%s\nLOG_LEVEL=info" % (E.d("mc").chars(32, HEX),
        E.d("mc2").chars(1, DIGITS)), "mailchimp")
    pfx(c, "Resend_Key", "Resend", "betterleaks resend & secrets-patterns-db",
        "api.resend.com", "RESEND_API_KEY", "re", 24, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bre_[A-Za-z0-9]{24,}\b", what="Resend 메일 API 키(`re_`).")
    pfx(c, "Postmark_Token", "Postmark", "gitleaks postmark & secrets-patterns-db",
        "api.postmarkapp.com", "POSTMARK_SERVER_TOKEN", "", 0, sev="High", ctx="header",
        regex=r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", flag="X-Postmark-Server-Token:",
        what="Postmark 서버 토큰(UUID). `X-Postmark-Server-Token` 헤더로 보낸다.",
        neg="00000000-0000-0000-0000-000000000000", var="X-Postmark-Server-Token")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "POST /email HTTP/1.1\nHost: api.postmarkapp.com\nX-Postmark-Server-Token: %s\nContent-Type: application/json"
        % E.uuid("postmark"), "postmark")
    pfx(c, "Notion_Token", "Notion", "secretlint secretlint-rule-notion & gitleaks notion-token",
        "api.notion.com", "NOTION_TOKEN", "ntn", 43, alph=ALNUM, sep="_", sev="High", ctx="json",
        regex=r"\bntn_[A-Za-z0-9]{43}\b", files=".cursor/mcp.json, claude_desktop_config.json, .env",
        what="Notion 통합 토큰(신형 `ntn_`, 구형 `secret_`). MCP 설정에 자주 들어간다.")
    pfx(c, "Airtable_PAT", "Airtable", "gitleaks airtable-api-key & secrets-patterns-db & nuclei airtable",
        "api.airtable.com", "AIRTABLE_TOKEN", "pat", 17, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"\bpat[A-Za-z0-9]{14}\.[a-f0-9]{64}\b", what="Airtable 개인 액세스 토큰(`pat` + 본문.체크섬).",
        neg="${AIRTABLE_TOKEN}", var="AIRTABLE_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nAIRTABLE_TOKEN=pat%s.%s\nLOG_LEVEL=info"
        % (E.d("at1").chars(14, ALNUM), E.d("at2").chars(64, HEX)), "airtable")
    pfx(c, "Linear_Key", "Linear", "secretlint secretlint-rule-linear & gitleaks linear-api-key",
        "api.linear.app", "LINEAR_API_KEY", "lin_api", 40, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\blin_api_[A-Za-z0-9]{40}\b", what="Linear 이슈 트래커 API 키(`lin_api_`).")
    pfx(c, "Atlassian_Token", "Atlassian", "gitleaks atlassian-api-token & secrets-patterns-db",
        "*.atlassian.net", "ATLASSIAN_API_TOKEN", "ATATT3xFfGF0", 180, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\bATATT3xFfGF0[A-Za-z0-9_\-=]{180,}\b", what="Atlassian(Jira/Confluence) API 토큰(`ATATT3xFfGF0`).")
    pfx(c, "HubSpot_Token", "HubSpot", "gitleaks hubspot-api-key & secrets-patterns-db",
        "api.hubapi.com", "HUBSPOT_TOKEN", "pat-na1", 0, sev="High", ctx="env",
        regex=r"\bpat-(na1|eu1)-[0-9a-f-]{36}\b", what="HubSpot private app 토큰(`pat-na1-` + UUID).",
        neg="${HUBSPOT_TOKEN}", var="HUBSPOT_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nHUBSPOT_TOKEN=pat-na1-%s\nLOG_LEVEL=info" % E.uuid("hubspot"), "hubspot")
    pfx(c, "Intercom_Token", "Intercom", "gitleaks intercom-api-key & secrets-patterns-db",
        "api.intercom.io", "INTERCOM_TOKEN", "dG9r", 0, alph=B64URL, sep="", sev="Medium", ctx="env",
        regex=r"\bdG9r[A-Za-z0-9+/=]{50,}\b", what="Intercom 액세스 토큰(base64, `dG9r`로 시작).",
        neg="${INTERCOM_TOKEN}", var="INTERCOM_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nINTERCOM_TOKEN=dG9r%s=\nLOG_LEVEL=info" % E.d("intercom").chars(80, ALNUM), "intercom")
    pfx(c, "Zendesk_Token", "Zendesk", "secrets-patterns-db zendesk & gitleaks",
        "*.zendesk.com", "ZENDESK_API_TOKEN", "", 40, alph=ALNUM, sep="", sev="Medium", ctx="env",
        regex=r"(?i)zendesk[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9]{40})",
        what="Zendesk API 토큰(40자).", neg="${ZENDESK_API_TOKEN}")
    add(c, "Solapi_API_Secret", "solapi/solapi-python (authenticator.py: HMAC-SHA256 ApiKey=..., signature=...)",
        "Solapi(쿨SMS) API Secret. API Key와 함께 HMAC-SHA256 서명을 만들어 `Authorization` 헤더에 넣는다.",
        "api.solapi.com", "SOLAPI_API_SECRET, api_secret, HMAC-SHA256",
        r"(?i)api_?secret\s*[:=]\s*['\"]?([A-Za-z0-9]{32,})",
        E.d("solapi").chars(32, ALNUM), "YOUR_API_SECRET", "High",
        ctx="py", var="api_secret", files="config.py, .env",
        guide="API Key(식별자, `Authorization: HMAC-SHA256 ApiKey=`에 그대로 노출)와 API Secret(서명 비밀)을 구분한다. secret만 마스킹한다.")
    pfx(c, "DingTalk_Robot_Secret", "DingTalk", "open-dingtalk/dingtalk-stream-sdk-python (Credential(client_id, client_secret))",
        "oapi.dingtalk.com", "DINGTALK_CLIENT_SECRET", "", 0, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\bSEC[a-f0-9]{64}\b", what="DingTalk(钉钉) 로봇/앱 시크릿. 웹훅 가입 로봇은 `SEC`+64hex 서명 비밀.",
        neg="${DINGTALK_CLIENT_SECRET}", var="DINGTALK_CLIENT_SECRET")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nDINGTALK_CLIENT_SECRET=SEC%s\nLOG_LEVEL=info" % E.d("dingtalk").chars(64, HEX), "dingtalk")
    pfx(c, "Lark_Feishu_App_Secret", "Lark", "larksuite/oapi-sdk-python (app_secret) & betterleaks lark-app-secret",
        "open.larksuite.com", "LARK_APP_SECRET", "", 32, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"(?i)(lark|feishu)[\w.\-]{0,20}secret['\"\s:=]{1,5}([A-Za-z0-9]{32})",
        what="Lark/Feishu(飞书) 앱 시크릿(32자). app_id와 짝으로 tenant token을 받는다.", neg="${LARK_APP_SECRET}",
        var="LARK_APP_SECRET")
    pfx(c, "WeChat_Corp_Secret", "Tencent", "nuclei wechat-corpsecret & github/docs tencent_wechat",
        "qyapi.weixin.qq.com", "WECHAT_CORP_SECRET", "", 43, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"(?i)corpsecret['\"\s:=]{1,5}([A-Za-z0-9_-]{43})",
        what="WeChat Work(企业微信) corpsecret(43자). corpid와 짝으로 access_token을 받는다.", neg="${WECHAT_CORP_SECRET}",
        var="corpsecret")
    pfx(c, "Chatwork_Token", "Chatwork", "chatwork/api (X-ChatWorkToken) & secrets-patterns-db",
        "api.chatwork.com", "CHATWORK_API_TOKEN", "", 40, alph=HEX, sep="", sev="Medium", ctx="header",
        regex=r"(?i)x-chatworktoken:+\s*([a-f0-9]{40})", flag="X-ChatWorkToken", var="X-ChatWorkToken",
        what="Chatwork API 토큰(40 hex). `X-ChatWorkToken` 헤더로 보낸다.", neg="<CHATWORK_TOKEN>")
    pfx(c, "Pusher_Secret", "Pusher", "gitleaks & secrets-patterns-db pusher",
        "*.pusher.com", "PUSHER_SECRET", "", 20, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)pusher[\w.\-]{0,20}secret['\"\s:=]{1,5}([a-f0-9]{20})",
        what="Pusher Channels secret(20 hex). app_id/key와 짝.", neg="${PUSHER_SECRET}", var="PUSHER_SECRET")
    pfx(c, "Ably_Key", "Ably", "secrets-patterns-db ably & gitleaks",
        "rest.ably.io", "ABLY_API_KEY", "", 0, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\b[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}:[A-Za-z0-9_+/-]{20,}\b",
        what="Ably API 키(`appId.keyId:keySecret` 구조). 콜론 뒤 secret이 핵심.", neg="${ABLY_API_KEY}",
        var="ABLY_API_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nABLY_API_KEY=%s.%s:%s\nLOG_LEVEL=info" % (E.d("ably1").chars(8, ALNUM),
        E.d("ably2").chars(8, ALNUM), E.d("ably3").chars(22, B64URL)), "ably")


def _observ(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "10"
    pfx(c, "Datadog_API_Key", "Datadog", "detect-secrets & gitleaks datadog-access-token & nuclei datadog",
        "api.datadoghq.com", "DD_API_KEY", "", 32, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)(dd|datadog)[_-]?api[_-]?key['\"\s:=]{1,5}([a-f0-9]{32})",
        what="Datadog API 키(32 hex). 짝인 APP 키(40 hex)와 함께 쓴다.", neg="${DD_API_KEY}", var="DD_API_KEY")
    pfx(c, "Datadog_APP_Key", "Datadog", "gitleaks & nuclei datadog",
        "api.datadoghq.com", "DD_APP_KEY", "", 40, alph=HEX, sep="", sev="High", ctx="env",
        regex=r"(?i)(dd|datadog)[_-]?app[_-]?key['\"\s:=]{1,5}([a-f0-9]{40})",
        what="Datadog 애플리케이션 키(40 hex).", neg="${DD_APP_KEY}", var="DD_APP_KEY")
    pfx(c, "NewRelic_License_Key", "New Relic", "gitleaks new-relic-* & secrets-patterns-db",
        "api.newrelic.com", "NEW_RELIC_LICENSE_KEY", "", 40, alph=ALNUM, sep="", sev="High", ctx="env",
        regex=r"\b[a-f0-9]{36}NRAL\b|\b[A-Za-z0-9]{40}\b", what="New Relic 라이선스 키(끝에 `NRAL`).",
        neg="${NEW_RELIC_LICENSE_KEY}", var="NEW_RELIC_LICENSE_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nNEW_RELIC_LICENSE_KEY=%sNRAL\nLOG_LEVEL=info" % E.d("nr").chars(36, HEX), "newrelic")
    pfx(c, "NewRelic_User_Key", "New Relic", "gitleaks new-relic-user-api-key",
        "api.newrelic.com", "NEW_RELIC_API_KEY", "NRAK", 27, alph=ALNUM, sep="-", sev="High", ctx="env",
        regex=r"\bNRAK-[A-Za-z0-9]{27}\b", what="New Relic 사용자 API 키(`NRAK-`).")
    pfx(c, "Dynatrace_Token", "Dynatrace", "gitleaks dynatrace-api-token & secrets-patterns-db",
        "*.live.dynatrace.com", "DT_API_TOKEN", "dt0c01", 24, alph=ALNUM, sep=".", sev="High", ctx="env",
        regex=r"\bdt0c01\.[A-Z0-9]{24}\.[A-Z0-9]{64}\b", what="Dynatrace API 토큰(`dt0c01.`).",
        neg="${DT_API_TOKEN}", var="DT_API_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nDT_API_TOKEN=dt0c01.%s.%s\nLOG_LEVEL=info"
        % (E.d("dt1").chars(24, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
           E.d("dt2").chars(64, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")), "dynatrace")
    pfx(c, "Grafana_Service_Account_Token", "Grafana", "secretlint secretlint-rule-grafana & gitleaks grafana-service-account-token",
        "*.grafana.net", "GRAFANA_TOKEN", "glsa", 32, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bglsa_[A-Za-z0-9]{32}_[A-Fa-f0-9]{8}\b", what="Grafana 서비스 계정 토큰(`glsa_`).",
        neg="${GRAFANA_TOKEN}", var="GRAFANA_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nGRAFANA_TOKEN=glsa_%s_%s\nLOG_LEVEL=info"
        % (E.d("gr1").chars(32, ALNUM), E.d("gr2").chars(8, HEX)), "grafana")
    add(c, "Sentry_DSN_And_Auth_Token", "gitleaks sentry-* & secrets-patterns-db",
        "Sentry DSN(공개 클라이언트 키 포함 URL)과 Auth Token(`sntrys_`)을 구분한다. DSN은 전송용 공개 키라 비밀이 아니다.",
        "*.sentry.io", "SENTRY_DSN, SENTRY_AUTH_TOKEN, sntrys_",
        r"\bsntrys_[A-Za-z0-9+/=]{60,}\b",
        "sntrys_" + E.d("sentry").chars(70, ALNUM + "+/="),
        "https://%s@o123.ingest.sentry.io/456" % E.d("sentrydsn").chars(32, HEX), "High",
        ctx="env", var="SENTRY_AUTH_TOKEN", negvar="SENTRY_DSN",
        guide="`sntrys_` Auth Token은 조직 관리 비밀이다. 반면 DSN URL 안의 공개 키는 클라이언트에 심는 값이라 마스킹하면 에러 리포트가 끊긴다.")
    add(c, "Cloudflare_API_Token", "osv-scalibr veles/cloudflareapitoken & secretlint secretlint-rule-cloudflare",
        "Cloudflare API 토큰(40자). 구형 Global API Key(37 hex)보다 권한이 좁지만 여전히 비밀이다.",
        "api.cloudflare.com", "CLOUDFLARE_API_TOKEN, CF_API_TOKEN",
        r"\b[A-Za-z0-9_-]{40}\b",
        E.d("cf").chars(40, ALNUM + "_-"), "${CF_API_TOKEN}",
        "High", ctx="env", var="CLOUDFLARE_API_TOKEN",
        guide="40자 영숫자라 일반 토큰과 길이가 겹친다. 변수명(CLOUDFLARE/CF)과 `api.cloudflare.com` 문맥으로 식별한다.")
    pfx(c, "Fastly_Token", "Fastly", "gitleaks fastly-api-token & secrets-patterns-db",
        "api.fastly.com", "FASTLY_API_TOKEN", "", 32, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"(?i)fastly[\w.\-]{0,20}['\"\s:=]{1,5}([A-Za-z0-9_-]{32})",
        what="Fastly API 토큰(32자).", neg="${FASTLY_API_TOKEN}")
    add(c, "Akamai_EdgeGrid_Secret", "gitleaks & secrets-patterns-db (akamai .edgerc)",
        "Akamai `.edgerc`의 client_secret. client_token/access_token과 함께 EdgeGrid 서명을 만든다.",
        "*.luna.akamaiapis.net", ".edgerc, client_secret, client_token",
        r"(?i)client_secret\s*=\s*([A-Za-z0-9+/=]{40,})",
        "%s=" % E.d("akamai").chars(43, ALNUM + "+/"), "${AKAMAI_CLIENT_SECRET}",
        "High", ctx="ini", var="client_secret", files="~/.edgerc",
        guide="`.edgerc`의 여러 값 중 client_secret만 서명 비밀이다. host·access_token은 식별자/별도 토큰이다.")
    pfx(c, "Mapbox_Secret_Token", "Mapbox", "detect-secrets & gitleaks mapbox",
        "api.mapbox.com", "MAPBOX_SECRET_TOKEN", "sk.", 0, alph=B64URL, sep="", sev="High", ctx="js",
        regex=r"\bsk\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b", var="MAPBOX_SECRET_TOKEN",
        what="Mapbox 비밀 토큰(`sk.`). 공개 토큰 `pk.`과 접두사로 구분된다.", neg="${MAPBOX_SECRET_TOKEN}")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        'const token = "sk.eyJ%s.%s";' % (E.d("mb1").chars(40, B64URL), E.d("mb2").chars(22, B64URL)), "mapbox")
    B.ROWS[-1]["SLM_Training_Guideline_KR"] = (
        "`sk.`(비밀)와 `pk.`(공개)를 구분한다. 지도 공개 토큰 `pk.`은 프런트엔드에 노출되는 설계라 마스킹하면 지도가 깨진다.")
    pfx(c, "Tailscale_Key", "Tailscale", "secretlint secretlint-rule-tailscale & gitleaks tailscale",
        "api.tailscale.com", "TS_AUTHKEY", "tskey-auth", 24, alph=B64URL, sep="-", sev="High", ctx="env",
        regex=r"\btskey-(auth|api|client)-[0-9A-Za-z]{8,}-[0-9A-Za-z]{16,}\b", var="TS_AUTHKEY",
        what="Tailscale 인증/API 키(`tskey-auth-`).", neg="${TS_AUTHKEY}")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nTS_AUTHKEY=tskey-auth-%s-%s\nLOG_LEVEL=info"
        % (E.d("ts1").chars(11, ALNUM), E.d("ts2").chars(22, ALNUM)), "tailscale")
    add(c, "WireGuard_Private_Key", "gitleaks & nuclei (wireguard wg0.conf)",
        "WireGuard `[Interface]`의 PrivateKey(44자 base64). PublicKey는 공유용이라 비밀이 아니다.",
        "VPN 피어", "PrivateKey, wg0.conf, [Interface]",
        r"(?i)PrivateKey\s*=\s*([A-Za-z0-9+/]{43}=)",
        "[Interface]\nAddress = 10.0.0.2/24\nPrivateKey = %s=" % E.b64url_bytes(E.d("wg").raw(32))
        .replace("-", "+").replace("_", "/"),
        "[Interface]\nAddress = 10.0.0.2/24\nPublicKey = %s=" % E.b64url_bytes(E.d("wgpub").raw(32))
        .replace("-", "+").replace("_", "/"), "High", ctx="stdout", var="cat", flag="cat /etc/wireguard/wg0.conf",
        channel="File_Read_Tool", fmt="INI", files="/etc/wireguard/wg0.conf",
        guide="`PrivateKey`만 비밀이다. 같은 44자 base64라도 `PublicKey`는 공유 전제라 마스킹하지 않는다. 키 이름이 결정적 단서다.")
    pfx(c, "Ngrok_Token", "ngrok", "gitleaks ngrok & secrets-patterns-db",
        "api.ngrok.com", "NGROK_AUTHTOKEN", "2", 0, alph=B64URL, sep="", sev="Medium", ctx="env",
        regex=r"\b2[A-Za-z0-9]{25,30}_[A-Za-z0-9]{20,30}\b", what="ngrok authtoken(`2...`).",
        neg="${NGROK_AUTHTOKEN}", var="NGROK_AUTHTOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env.production\nNGROK_AUTHTOKEN=2%s_%s\nLOG_LEVEL=info"
        % (E.d("ngrok1").chars(26, ALNUM), E.d("ngrok2").chars(24, ALNUM)), "ngrok")


def _crypto(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "11"
    for label, sub, kr, tag in (("RSA PRIVATE KEY", "PEM_RSA_Private_Key", "RSA 개인 키", "rsa"),
                                ("EC PRIVATE KEY", "PEM_EC_Private_Key", "EC(타원곡선) 개인 키", "ec"),
                                ("PRIVATE KEY", "PEM_PKCS8_Private_Key", "PKCS#8 개인 키", "pkcs8"),
                                ("DSA PRIVATE KEY", "PEM_DSA_Private_Key", "DSA 개인 키", "dsa")):
        add(c, sub, "secretlint secretlint-rule-privatekey & gitleaks private-key & microsoft/security-utilities",
            f"PEM 형식 {kr}. `-----BEGIN {label}-----`와 `-----END-----` 사이 base64 본문 전체가 비밀이다.",
            "짝인 공개 인증서/호스트", f"-----BEGIN {label}-----",
            rf"-----BEGIN {label}-----[\s\S]+?-----END {label}-----",
            E.pem(label, tag), "-----BEGIN PUBLIC KEY-----\n" + E._pem_body("pub" + tag, 60) + "\n-----END PUBLIC KEY-----",
            "Critical", ctx="stdout", var="cat", flag=f"cat id_{tag}", channel="File_Read_Tool", fmt="PEM",
            files=f"id_{tag}, *.pem, *.key",
            guide=f"`BEGIN {label}`로 시작하는 블록은 비밀이다. Hard Negative인 `BEGIN PUBLIC KEY`/인증서는 공유용이라 마스킹하지 않는다. "
                  f"헤더의 PRIVATE vs PUBLIC 한 단어가 결정적이다.")
    add(c, "OpenSSH_Private_Key", "gitleaks & microsoft/security-utilities & noseyparker",
        "OpenSSH 신형 개인 키(`-----BEGIN OPENSSH PRIVATE KEY-----`). `ssh-keygen` 기본 형식.",
        "SSH 접속 대상 호스트", "-----BEGIN OPENSSH PRIVATE KEY-----, id_ed25519",
        r"-----BEGIN OPENSSH PRIVATE KEY-----[\s\S]+?-----END OPENSSH PRIVATE KEY-----",
        E.openssh_key("openssh"), "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI%s deploy@host"
        % E.d("sshpub").chars(43, B64URL), "Critical", ctx="stdout", var="cat", flag="cat ~/.ssh/id_ed25519",
        channel="File_Read_Tool", fmt="PEM", files="~/.ssh/id_ed25519, ~/.ssh/id_rsa",
        guide="개인 키 블록은 비밀이다. Hard Negative인 `ssh-ed25519 AAAA...` 공개 키(authorized_keys/`*.pub`)는 공유용이라 마스킹하지 않는다.")
    add(c, "PuTTY_PPK_Private_Key", "gitleaks & secrets-patterns-db (putty ppk)",
        "PuTTY `.ppk` 키 파일의 `Private-Lines` 블록. Windows SSH 클라이언트가 쓰는 개인 키다.",
        "SSH 접속 대상 호스트", "PuTTY-User-Key-File, Private-Lines",
        r"(?s)Private-Lines:\s*\d+\n([A-Za-z0-9+/=\n]+)Private-MAC",
        "PuTTY-User-Key-File-3: ssh-ed25519\nPrivate-Lines: 1\n%s\nPrivate-MAC: %s"
        % (E._pem_body("ppk", 48), E.d("ppkmac").chars(64, HEX)),
        "PuTTY-User-Key-File-3: ssh-ed25519\nPublic-Lines: 2\n%s" % E._pem_body("ppkpub", 48),
        "Critical", ctx="stdout", var="cat", flag="cat deploy.ppk", channel="File_Read_Tool", fmt="PPK",
        files="*.ppk", guide="`Private-Lines` 본문이 비밀이다. `Public-Lines` 블록은 공유용 공개 키라 마스킹하지 않는다.")
    add(c, "JWT_HS256_Signed", "secretlint secretlint-rule-jwt & gitleaks jwt & osv-scalibr veles/jwt",
        "서명이 붙은 JWT(`header.payload.signature`). payload는 base64라 디코딩되지만 서명·용도에 따라 세션 토큰이면 비밀이다.",
        "토큰을 검증하는 API", "eyJ, Bearer, jwt",
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        E.jwt("jwt_hs", extra={"scope": "admin", "name": "svc"}),
        "eyJhbGciOiJub25lIn0.eyJzdWIiOiJkb2NzIn0.", "High", ctx="env", var="JWT_TOKEN", fmt="JWT",
        guide="세 세그먼트(점 2개)가 한 토큰이다. 서명(세 번째)이 있고 세션/액세스 용도면 비밀이다. `alg:none`에 서명이 빈 예시 토큰은 비밀이 아니다.")
    add(c, "JWK_Private_Key_Material", "gitleaks & RFC7517 (JWK 'd' parameter)",
        "JWK(JSON Web Key)의 개인 파라미터. RSA는 `d`,`p`,`q`, EC는 `d`가 개인 비밀이다. `x`,`y`,`n`,`e`는 공개값.",
        "JWKS를 쓰는 인증 서버", "\"d\":, \"kty\":, jwk",
        r"\"kty\"\s*:\s*\"(RSA|EC|OKP)\".*\"d\"\s*:\s*\"([A-Za-z0-9_-]{20,})\"",
        '{\n  "kty": "EC", "crv": "P-256",\n  "x": "%s",\n  "d": "%s"\n}'
        % (E.d("jwkx").chars(43, B64URL), E.d("jwkd").chars(43, B64URL)),
        '{\n  "kty": "EC", "crv": "P-256",\n  "x": "%s",\n  "y": "%s"\n}'
        % (E.d("jwkx2").chars(43, B64URL), E.d("jwky").chars(43, B64URL)), "Critical", ctx="stdout",
        var="cat", flag="cat jwk.json", channel="File_Read_Tool", fmt="JWK / JSON", files="jwk.json, jwks.json",
        guide="같은 JWK라도 `d`(개인 지수)가 있으면 비밀, `x`/`y`/`n`/`e`만 있으면 공개 키다. 필드 이름으로 판단하도록 학습한다.")
    pfx(c, "Auth0_Client_Secret", "Auth0", "gitleaks & secrets-patterns-db auth0",
        "*.auth0.com", "AUTH0_CLIENT_SECRET", "", 64, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"(?i)auth0[\w.\-]{0,20}secret['\"\s:=]{1,5}([A-Za-z0-9_-]{48,})",
        what="Auth0 애플리케이션 client secret(64자).", neg="${AUTH0_CLIENT_SECRET}", var="AUTH0_CLIENT_SECRET")
    pfx(c, "Okta_API_Token", "Okta", "gitleaks okta-access-token & secrets-patterns-db",
        "*.okta.com", "OKTA_API_TOKEN", "00", 40, alph=B64URL, sep="", sev="High", ctx="env",
        regex=r"\b00[A-Za-z0-9_-]{40}\b", what="Okta API 토큰(`00` 시작, 42자).", neg="${OKTA_API_TOKEN}")
    add(c, "OAuth2_Client_Secret_Generic", "gitleaks & nuclei (oauth client_secret)",
        "범용 OAuth2 client_secret. client_id(공개)와 짝이며 토큰 교환 시 쓰는 비밀이다.",
        "OAuth2 토큰 엔드포인트", "client_secret, client_id, grant_type",
        r"(?i)client_secret\W{0,3}[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})",
        E.tok("", 40, ALNUM, tag="oauth_cs"), "${OAUTH_CLIENT_SECRET}", "High", ctx="json", var="client_secret",
        guide="client_id는 공개 식별자, client_secret만 비밀이다. 둘이 한 블록에 있어도 secret span만 고른다.")
    add(c, "Netrc_Machine_Password", "whispers (uri.py) & gitleaks & SecretBench (.netrc)",
        "`~/.netrc`의 machine/login/password 3요소. password 값이 비밀이고 git·curl·huggingface가 참조한다.",
        ".netrc의 machine 호스트", "machine, login, password, .netrc",
        r"machine\s+\S+\s+login\s+\S+\s+password\s+(\S+)",
        "machine api.internal\n  login svc_deploy\n  password %s" % E.password("netrc", "random"),
        "machine api.internal\n  login svc_deploy\n  password ${NETRC_PASSWORD}", "High", ctx="stdout",
        var="cat", flag="cat ~/.netrc", channel="File_Read_Tool", fmt="netrc", files="~/.netrc, ~/.config/netrc",
        guide="machine(호스트)·login(아이디)은 식별자, password 값만 비밀이다. 토큰 인증 시 password 자리에 토큰이 올 수도 있다.")
    add(c, "Shadow_File_Hash", "gitleaks & SecretBench (/etc/shadow)",
        "`/etc/shadow`의 비밀번호 해시(`$6$`/`$y$`/`$2b$`). 평문은 아니지만 오프라인 크래킹 대상이라 민감하다.",
        "리눅스 로컬 계정", "/etc/shadow, $6$, $y$",
        r"^[a-z_][a-z0-9_-]*:\$(6|y|2[aby]|1)\$[^:]+:",
        "root:$6$%s$%s:19876:0:99999:7:::" % (E.d("shadow1").chars(16, ALNUM + "./"),
        E.d("shadow2").chars(86, ALNUM + "./")),
        "daemon:*:19000:0:99999:7:::", "High", ctx="stdout", var="cat", flag="sudo cat /etc/shadow",
        channel="File_Read_Tool / Bash_Tool_Stdout", fmt="shadow", files="/etc/shadow",
        guide="`$6$...` 같은 해시 필드는 민감하다. 비밀번호가 없어 `*`나 `!`인 계정(로그인 불가)은 비밀이 아니다. 둘째 필드의 내용이 단서다.")
    add(c, "John_Hashcat_Potfile", "Hashcat/JohnTheRipper potfile output",
        "john/hashcat potfile — `해시:크랙된평문` 줄. 콜론 뒤 복구된 평문 비밀번호가 비밀이다.",
        "크래킹 대상 시스템", "john.pot, hashcat.potfile, cracked",
        r"^\$[0-9a-z]+\$[^\:]+:(.+)$",
        "$6$%s$%s:%s" % (E.d("pot1").chars(8, ALNUM), E.d("pot2").chars(43, ALNUM + "./"),
        E.password("pot3", "weak")),
        "$6$salt$hash:(not cracked)", "High", ctx="stdout", var="cat", flag="cat john.pot",
        channel="File_Read_Tool / Bash_Tool_Stdout", fmt="potfile", files="~/.john/john.pot, hashcat.potfile",
        guide="해시 자체가 아니라 콜론 뒤 크랙된 평문이 실제 비밀번호다. `(not cracked)` 같은 미복구 표시는 비밀이 아니다.")


def _mobile(B):
    E = B.E; pfx = B.pfx; add = B.add
    HEX, ALNUM, B64, B64URL, BASE32, DIGITS = E.HEX, E.ALNUM, E.B64, E.B64URL, E.BASE32, E.DIGITS
    c = "13"
    add(c, "Firebase_Google_Services_JSON", "gitleaks & nuclei (google-services.json)",
        "Android `google-services.json`의 `current_key`(AIza 형식). 앱에 포함돼 배포되지만 제한 설정이 없으면 남용된다.",
        "firebaseio.com / googleapis.com", "google-services.json, current_key, api_key",
        r"\"current_key\":\s*\"(AIza[0-9A-Za-z_-]{35})\"",
        '{\n  "api_key": [{ "current_key": "AIza%s" }]\n}' % E.d("fbkey").chars(35, B64URL),
        '{\n  "api_key": [{ "current_key": "YOUR_API_KEY" }]\n}', "High", ctx="stdout", var="cat",
        flag="cat app/google-services.json", channel="File_Read_Tool", fmt="JSON",
        files="app/google-services.json, GoogleService-Info.plist",
        guide="`current_key`의 `AIza` 키는 앱에 번들되지만 API 제한이 없으면 비밀처럼 다뤄야 한다. `YOUR_API_KEY` 자리표시는 제외한다.")
    add(c, "Firebase_Admin_SDK_Private_Key", "gitleaks gcp-service-account & Firebase Admin SDK",
        "Firebase Admin SDK 서비스 계정 JSON. `private_key`에 PEM이 들어 서버 전체 권한을 가진다.",
        "*.firebaseio.com", "firebase-adminsdk, private_key, service_account",
        r"\"private_key\":\s*\"-----BEGIN PRIVATE KEY-----",
        '{\n  "type": "service_account",\n  "client_email": "firebase-adminsdk@proj.iam.gserviceaccount.com",\n  "private_key": "-----BEGIN PRIVATE KEY-----\\n%s\\n-----END PRIVATE KEY-----\\n"\n}'
        % E._pem_body("fbadmin", 120).replace("\n", "\\n"),
        '{\n  "type": "service_account",\n  "private_key": "${FIREBASE_PRIVATE_KEY}"\n}', "Critical",
        ctx="stdout", var="cat", flag="cat firebase-adminsdk.json", channel="File_Read_Tool", fmt="JSON",
        files="firebase-adminsdk-*.json, serviceAccountKey.json",
        guide="Admin SDK 키의 `private_key` PEM은 Critical이다. 앱에 넣는 `google-services.json`(AIza)과 혼동하지 말고 둘을 구분해 학습한다.")
    add(c, "Android_Keystore_Password", "gitleaks & nuclei (gradle signingConfigs / keystore.properties)",
        "Android 서명 keystore 비밀번호. `keystore.properties`의 storePassword/keyPassword가 앱 서명 키를 연다.",
        "Google Play 서명", "storePassword, keyPassword, keystore.properties",
        r"(?i)(store|key)Password\s*=\s*(\S+)",
        "storePassword=%s\nkeyPassword=%s\nkeyAlias=upload" % (E.password("ks1", "random"), E.password("ks2", "random")),
        "storePassword=${KEYSTORE_PASSWORD}\nkeyPassword=${KEY_PASSWORD}", "High", ctx="stdout", var="cat",
        flag="cat keystore.properties", channel="File_Read_Tool", fmt="Properties",
        files="keystore.properties, local.properties, build.gradle",
        guide="storePassword/keyPassword 값만 비밀이다. keyAlias(식별자)와 `${...}` 참조는 제외한다.")
    pfx(c, "iOS_AppStore_Connect_P8", "Apple", "gitleaks & fastlane (AuthKey_*.p8)",
        "appstoreconnect.apple.com", "APP_STORE_CONNECT_KEY", "", 0, sev="Critical", ctx="stdout",
        regex=r"-----BEGIN PRIVATE KEY-----[\s\S]+?-----END PRIVATE KEY-----", flag="cat AuthKey_ABC123.p8",
        channel="File_Read_Tool", what="App Store Connect API 키(`AuthKey_*.p8`, EC 개인 키). Fastlane 배포 자동화에 쓴다.",
        neg="${APP_STORE_CONNECT_KEY}", var="cat", files="AuthKey_*.p8, fastlane/", fmt="PEM")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "$ cat AuthKey_ABC1234DEF.p8\n%s" % E.pem("PRIVATE KEY", "ios_p8", 120), "ios_p8")
    pfx(c, "Expo_EAS_Token", "Expo", "secrets-patterns-db expo",
        "expo.dev", "EXPO_TOKEN", "", 0, sev="High", ctx="env",
        regex=r"(?i)expo[\w.\-]{0,10}token['\"\s:=]{1,5}([A-Za-z0-9_-]{30,})",
        what="Expo EAS 액세스 토큰. React Native 빌드/배포 자동화 권한.", neg="${EXPO_TOKEN}", var="EXPO_TOKEN")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env\nEXPO_TOKEN=%s\nLOG_LEVEL=info" % E.tok("", 40, B64URL, tag="expo"), "expo")
    pfx(c, "RevenueCat_Key", "RevenueCat", "secrets-patterns-db revenuecat",
        "api.revenuecat.com", "REVENUECAT_SECRET_KEY", "sk", 24, alph=ALNUM, sep="_", sev="High", ctx="env",
        regex=r"\bsk_[A-Za-z0-9]{24,}\b", what="RevenueCat 시크릿 API 키(`sk_`). 공개 SDK 키(`appl_`/`goog_`)와 구분.")
    pfx(c, "OneSignal_REST_Key", "OneSignal", "secrets-patterns-db onesignal",
        "onesignal.com/api", "ONESIGNAL_REST_API_KEY", "os_v2_app", 0, alph=B64URL, sep="_", sev="High", ctx="env",
        regex=r"\bos_v2_app_[a-z0-9_]{40,}\b", what="OneSignal REST API 키(`os_v2_app_`). 푸시 발송 권한.",
        neg="${ONESIGNAL_REST_API_KEY}", var="ONESIGNAL_REST_API_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        "# .env\nONESIGNAL_REST_API_KEY=os_v2_app_%s\nLOG_LEVEL=info" % E.d("onesignal").chars(60, "abcdefghijklmnopqrstuvwxyz0123456789_"), "onesignal")
    add(c, "Web3_EVM_Private_Key", "gitleaks & secrets-patterns-db (ethereum private key)",
        "이더리움/EVM 지갑 개인 키(`0x` + 64 hex). 이 키 하나로 지갑 자산을 전부 이전할 수 있다.",
        "EVM 체인 RPC", "PRIVATE_KEY, 0x, wallet, hardhat",
        r"\b0x[a-fA-F0-9]{64}\b",
        "0x%s" % E.d("evm").chars(64, HEX),
        "0x%s" % E.d("evmaddr").chars(40, HEX), "Critical", ctx="env", var="PRIVATE_KEY", negvar="WALLET_ADDRESS",
        files="hardhat.config.js, .env, foundry.toml",
        guide="`0x`+64 hex 개인 키는 Critical이다. `0x`+40 hex 지갑 주소는 공개 식별자라 비밀이 아니다. hex 길이(64 vs 40)가 결정적이다.")
    add(c, "BIP39_Mnemonic_Seed", "gitleaks & secrets-patterns-db (mnemonic seed phrase)",
        "BIP39 니모닉 시드 구문(12/24 영어 단어). 지갑 전체를 복구하는 최상위 비밀이다.",
        "HD 지갑", "mnemonic, seed phrase, MNEMONIC",
        r"(?i)mnemonic\s*[:=]\s*['\"]((?:[a-z]+\s){11,23}[a-z]+)['\"]",
        '"%s"' % " ".join(E.d("bip39").choice(("abandon", "ability", "able", "about", "above", "absorb",
        "abstract", "absurd", "abuse", "access", "accident", "account", "accuse", "achieve", "acid", "acoustic",
        "acquire", "across", "action", "actor", "adapt", "addict", "address", "adjust")) for _ in range(12)),
        '"<your twelve word seed phrase goes here for testing only>"', "Critical", ctx="env",
        var="MNEMONIC", files=".env, hardhat.config.js, wallet backup",
        guide="공백으로 이어진 11~23개 영어 단어 뒤 한 단어(총 12/24개)가 시드다. 단어 하나하나는 흔하지만 BIP39 단어목록 구성이 단서다. "
              "테스트 안내문 같은 자유 문장은 니모닉이 아니다.")
    pfx(c, "Alchemy_Key", "Alchemy", "secrets-patterns-db alchemy & gitleaks",
        "*.g.alchemy.com", "ALCHEMY_API_KEY", "", 32, alph=B64URL, sep="", sev="High", ctx="js",
        regex=r"https://eth-mainnet\.g\.alchemy\.com/v2/([A-Za-z0-9_-]{32})",
        what="Alchemy RPC API 키. RPC URL 경로(`/v2/<key>`)에 박혀 노출되기 쉽다.", neg="${ALCHEMY_API_KEY}",
        var="ALCHEMY_API_KEY")
    B.ROWS[-1]["Synthetic_Positive_Example_Raw"] = B._unique(
        'const url = "https://eth-mainnet.g.alchemy.com/v2/%s";' % E.d("alchemy").chars(32, B64URL), "alchemy")
    add(c, "Embedded_C_Header_Define_Key", "WrongSecrets & embedded firmware (#define API_KEY)",
        "임베디드 C/C++ 헤더의 `#define`에 하드코딩된 키. 펌웨어에 그대로 박혀 추출 가능하다.",
        "IoT 디바이스가 붙는 클라우드", "#define, API_KEY, WIFI_PASS",
        r"#define\s+\w*(API_KEY|SECRET|PASS|TOKEN)\w*\s+\"([^\"]{8,})\"",
        '#define WIFI_SSID "factory-iot"\n#define WIFI_PASS "%s"\n#define DEVICE_API_KEY "%s"'
        % (E.password("cwifi", "random"), E.tok("", 32, ALNUM, tag="cdev")),
        '#define WIFI_SSID "factory-iot"\n#define WIFI_PASS ""\n#define DEVICE_API_KEY "CHANGEME"',
        "High", ctx="stdout", var="cat", flag="cat include/secrets.h", channel="File_Read_Tool", fmt="C Header",
        files="include/secrets.h, config.h, platformio.ini",
        guide="`#define`의 문자열 리터럴이 비밀이다. 빈 문자열이나 `CHANGEME` 같은 자리표시는 제외한다. 매크로 이름이 비밀 성격을 알려준다.")
    add(c, "WebRTC_TURN_Credential", "gitleaks & nuclei (turn server credential)",
        "WebRTC TURN 서버 자격증명. `turn:` URL과 함께 쓰는 username/credential의 credential이 비밀이다.",
        "coturn/TURN 서버", "iceServers, turn:, credential, username",
        r"\"credential\"\s*:\s*\"([^\"]{8,})\"",
        '{\n  "iceServers": [{\n    "urls": "turn:turn.internal:3478",\n    "username": "webrtc",\n    "credential": "%s"\n  }]\n}'
        % E.password("turn", "random"),
        '{\n  "iceServers": [{\n    "urls": "stun:stun.internal:3478"\n  }]\n}', "Medium", ctx="stdout",
        var="cat", flag="cat ice-config.json", channel="File_Read_Tool", fmt="JSON", files="ice-config.json",
        guide="`credential` 값만 비밀이다. `urls`·`username`은 식별자이고, STUN 서버는 자격증명이 없어 음성이다.")

