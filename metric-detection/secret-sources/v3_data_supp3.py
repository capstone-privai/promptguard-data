"""Supplement 3: additional well-known service token types (one row each) to reach the 600+ goal. Prefixes
and formats are from the scanner catalogs and public vendor docs gathered in discovery; values are deterministic
fakes. populate(B) appends to B.ROWS.

Each tuple: (cat, sub, vendor, host, env_name, prefix, sep, n, alpha, sev). When prefix is "" the row keys on a
keyword-context regex built from env_name's vendor token instead of a prefix.
"""

# (cat, sub, vendor, host, env, prefix, sep, n, alpha, sev)
T = [
    # --- 02 AI / ML / vector ---
    ("02", "Clerk_Secret_Key", "Clerk", "api.clerk.com", "CLERK_SECRET_KEY", "sk_live", "_", 40, "ALNUM", "Critical"),
    ("02", "WorkOS_Key", "WorkOS", "api.workos.com", "WORKOS_API_KEY", "sk_live", "_", 40, "ALNUM", "High"),
    ("02", "Cerebras_Key", "Cerebras", "api.cerebras.ai", "CEREBRAS_API_KEY", "csk", "-", 40, "B64URL", "High"),
    ("02", "AnyscaleModal_Token", "Modal", "modal.com", "MODAL_TOKEN_SECRET", "as", "-", 32, "ALNUM", "High"),
    ("02", "Baseten_Key", "Baseten", "app.baseten.co", "BASETEN_API_KEY", "", "", 40, "HEX", "High"),
    ("02", "DeepInfra_Token", "DeepInfra", "api.deepinfra.com", "DEEPINFRA_TOKEN", "", "", 32, "ALNUM", "High"),
    ("02", "AI21_Key", "AI21", "api.ai21.com", "AI21_API_KEY", "", "", 32, "ALNUM", "High"),
    ("02", "Writer_Key", "Writer", "api.writer.com", "WRITER_API_KEY", "", "", 40, "HEX", "High"),
    ("02", "Nomic_Key", "Nomic", "api-atlas.nomic.ai", "NOMIC_API_KEY", "nk", "-", 40, "B64URL", "High"),
    ("02", "LlamaCloud_Key", "LlamaIndex", "cloud.llamaindex.ai", "LLAMA_CLOUD_API_KEY", "llx", "-", 48, "ALNUM", "High"),
    ("02", "Fireworks_Account_Key", "Fireworks", "api.fireworks.ai", "FIREWORKS_ACCOUNT_KEY", "fw", "_", 40, "ALNUM", "High"),
    ("02", "Weaviate_Cloud_Key", "Weaviate", "*.weaviate.cloud", "WEAVIATE_API_KEY", "wcs", "-", 40, "B64URL", "High"),
    ("02", "Qdrant_Cloud_Key", "Qdrant", "*.qdrant.io", "QDRANT_API_KEY", "", "", 0, "JWT", "High"),
    ("02", "Hasura_Admin_Secret", "Hasura", "*.hasura.app", "HASURA_GRAPHQL_ADMIN_SECRET", "", "", 32, "ALNUM", "Critical"),
    ("02", "Appwrite_API_Key", "Appwrite", "cloud.appwrite.io", "APPWRITE_API_KEY", "", "", 64, "HEX", "High"),
    ("02", "Fal_Key", "fal.ai", "fal.run", "FAL_KEY", "", "", 0, "FALPAIR", "High"),
    ("02", "SegmindToken", "Segmind", "api.segmind.com", "SEGMIND_API_KEY", "sg_", "", 32, "HEX", "Medium"),
    # --- 03 cloud ---
    ("03", "Vultr_Key", "Vultr", "api.vultr.com", "VULTR_API_KEY", "", "", 36, "ALNUM", "High"),
    ("03", "Hetzner_Token", "Hetzner", "api.hetzner.cloud", "HCLOUD_TOKEN", "", "", 64, "ALNUM", "High"),
    ("03", "UpCloud_Password", "UpCloud", "api.upcloud.com", "UPCLOUD_PASSWORD", "", "", 24, "ALNUM", "High"),
    ("03", "OVH_Application_Secret", "OVH", "api.ovh.com", "OVH_APPLICATION_SECRET", "", "", 32, "ALNUM", "High"),
    ("03", "Yandex_IAM_Key", "Yandex", "iam.api.cloud.yandex.net", "YANDEX_OAUTH_TOKEN", "y0_", "", 70, "B64URL", "High"),
    ("03", "Exoscale_Secret", "Exoscale", "api.exoscale.com", "EXOSCALE_API_SECRET", "", "", 40, "B64URL", "High"),
    ("03", "Civo_Token", "Civo", "api.civo.com", "CIVO_TOKEN", "", "", 64, "ALNUM", "High"),
    # --- 04 db / baas ---
    ("04", "Xata_Key", "Xata", "*.xata.sh", "XATA_API_KEY", "xau", "_", 37, "B64URL", "High"),
    ("04", "FaunaDB_Key", "Fauna", "db.fauna.com", "FAUNA_SECRET", "fn", "", 40, "B64URL", "High"),
    ("04", "TiDB_Cloud_Password", "TiDB", "*.tidbcloud.com", "TIDB_PASSWORD", "", "", 24, "ALNUM", "High"),
    ("04", "Nhost_Admin_Secret", "Nhost", "*.nhost.run", "NHOST_ADMIN_SECRET", "", "", 32, "ALNUM", "High"),
    ("04", "Directus_Static_Token", "Directus", "*.directus.app", "DIRECTUS_TOKEN", "", "", 32, "ALNUM", "High"),
    ("04", "Tinybird_Token", "Tinybird", "api.tinybird.co", "TINYBIRD_TOKEN", "p", ".", 0, "JWT", "High"),
    ("04", "MotherDuck_Token", "MotherDuck", "motherduck.com", "MOTHERDUCK_TOKEN", "", "", 0, "JWT", "High"),
    ("04", "SingleStore_Password", "SingleStore", "*.singlestore.com", "SINGLESTORE_PASSWORD", "", "", 24, "ALNUM", "High"),
    ("04", "Rockset_Key", "Rockset", "api.rs2.usw2.rockset.com", "ROCKSET_API_KEY", "", "", 40, "ALNUM", "High"),
    # --- 05 vcs / ci / build ---
    ("05", "AzureDevOps_PAT", "Azure DevOps", "dev.azure.com", "AZURE_DEVOPS_PAT", "", "", 52, "B64URL", "High"),
    ("05", "Cloudsmith_Key", "Cloudsmith", "api.cloudsmith.io", "CLOUDSMITH_API_KEY", "", "", 40, "HEX", "High"),
    ("05", "Gemfury_Token", "Gemfury", "api.fury.io", "GEMFURY_TOKEN", "", "", 40, "ALNUM", "High"),
    ("05", "Turbo_Token", "Turborepo", "vercel.com/api", "TURBO_TOKEN", "", "", 24, "ALNUM", "High"),
    ("05", "Chromatic_Token", "Chromatic", "www.chromatic.com", "CHROMATIC_PROJECT_TOKEN", "chpt", "_", 40, "HEX", "High"),
    ("05", "Percy_Token", "Percy", "percy.io", "PERCY_TOKEN", "percy_pat", "_", 64, "HEX", "High"),
    ("05", "Bitrise_Token", "Bitrise", "api.bitrise.io", "BITRISE_TOKEN", "", "", 43, "B64URL", "High"),
    ("05", "Semaphore_Token", "Semaphore", "*.semaphoreci.com", "SEMAPHORE_API_TOKEN", "", "", 20, "ALNUM", "High"),
    ("05", "Codeberg_Token", "Codeberg", "codeberg.org", "CODEBERG_TOKEN", "", "", 40, "HEX", "High"),
    ("05", "AppCenter_Token", "App Center", "api.appcenter.ms", "APPCENTER_TOKEN", "", "", 40, "HEX", "High"),
    # --- 06 secret mgr / infra ---
    ("06", "Akeyless_Token", "Akeyless", "api.akeyless.io", "AKEYLESS_TOKEN", "t-", "", 40, "ALNUM", "High"),
    ("06", "Spacelift_Token", "Spacelift", "*.app.spacelift.io", "SPACELIFT_API_TOKEN", "", "", 0, "JWT", "High"),
    ("06", "Env0_Key", "env0", "api.env0.com", "ENV0_API_KEY", "", "", 40, "ALNUM", "High"),
    ("06", "Teleport_Token", "Teleport", "*.teleport.sh", "TELEPORT_TOKEN", "", "", 32, "HEX", "High"),
    ("06", "CyberArk_Conjur_Key", "CyberArk", "conjur.internal", "CONJUR_API_KEY", "", "", 44, "B64URL", "High"),
    # --- 07 auth / enterprise ---
    ("07", "Stytch_Secret", "Stytch", "api.stytch.com", "STYTCH_SECRET", "secret-live", "-", 44, "B64URL", "Critical"),
    ("07", "FusionAuth_Key", "FusionAuth", "*.fusionauth.io", "FUSIONAUTH_API_KEY", "", "", 0, "JWT", "High"),
    ("07", "Ory_Key", "Ory", "*.projects.oryapis.com", "ORY_API_KEY", "ory_pat", "_", 43, "B64URL", "High"),
    ("07", "Descope_Key", "Descope", "api.descope.com", "DESCOPE_MANAGEMENT_KEY", "K", "", 40, "ALNUM", "High"),
    ("07", "Kinde_Secret", "Kinde", "*.kinde.com", "KINDE_CLIENT_SECRET", "", "", 48, "B64URL", "High"),
    ("07", "SuperTokens_Key", "SuperTokens", "*.supertokens.io", "SUPERTOKENS_API_KEY", "", "", 40, "ALNUM", "High"),
    # --- 08 fintech / payment ---
    ("08", "Razorpay_Key_Secret", "Razorpay", "api.razorpay.com", "RAZORPAY_KEY_SECRET", "", "", 24, "ALNUM", "Critical"),
    ("08", "Checkout_Secret_Key", "Checkout.com", "api.checkout.com", "CKO_SECRET_KEY", "sk_", "", 36, "HEX", "Critical"),
    ("08", "Mollie_Key", "Mollie", "api.mollie.com", "MOLLIE_API_KEY", "live", "_", 30, "ALNUM", "Critical"),
    ("08", "GoCardless_Token", "GoCardless", "api.gocardless.com", "GOCARDLESS_TOKEN", "live", "_", 40, "B64URL", "High"),
    ("08", "Xendit_Key", "Xendit", "api.xendit.co", "XENDIT_SECRET_KEY", "xnd_production", "_", 40, "B64URL", "Critical"),
    ("08", "Omise_Secret_Key", "Omise", "api.omise.co", "OMISE_SECRET_KEY", "skey_live", "_", 32, "ALNUM", "Critical"),
    ("08", "Midtrans_Server_Key", "Midtrans", "api.midtrans.com", "MIDTRANS_SERVER_KEY", "Mid-server", "-", 24, "B64URL", "Critical"),
    ("08", "Paddle_Key", "Paddle", "api.paddle.com", "PADDLE_API_KEY", "pdl_live_apikey", "_", 50, "ALNUM", "High"),
    ("08", "LemonSqueezy_Key", "Lemon Squeezy", "api.lemonsqueezy.com", "LEMONSQUEEZY_API_KEY", "", "", 0, "JWT", "High"),
    ("08", "Chargebee_Key", "Chargebee", "*.chargebee.com", "CHARGEBEE_API_KEY", "live_", "", 32, "ALNUM", "High"),
    ("08", "Wise_Token", "Wise", "api.wise.com", "WISE_API_TOKEN", "", "", 0, "UUID", "High"),
    # --- 09 messaging / crm ---
    ("09", "Klaviyo_Private_Key", "Klaviyo", "a.klaviyo.com", "KLAVIYO_PRIVATE_KEY", "pk_", "", 34, "B64URL", "High"),
    ("09", "Brevo_Key", "Brevo", "api.brevo.com", "BREVO_API_KEY", "xkeysib", "-", 64, "B64URL", "High"),
    ("09", "MailerSend_Token", "MailerSend", "api.mailersend.com", "MAILERSEND_API_KEY", "mlsn", ".", 64, "HEX", "High"),
    ("09", "SparkPost_Key", "SparkPost", "api.sparkpost.com", "SPARKPOST_API_KEY", "", "", 40, "HEX", "High"),
    ("09", "Telnyx_Key", "Telnyx", "api.telnyx.com", "TELNYX_API_KEY", "KEY", "", 40, "B64URL", "High"),
    ("09", "Plivo_Auth_Token", "Plivo", "api.plivo.com", "PLIVO_AUTH_TOKEN", "", "", 40, "B64URL", "High"),
    ("09", "Vonage_Secret", "Vonage", "api.nexmo.com", "VONAGE_API_SECRET", "", "", 16, "ALNUM", "High"),
    ("09", "Infobip_Key", "Infobip", "*.api.infobip.com", "INFOBIP_API_KEY", "", "", 32, "HEX", "High"),
    ("09", "Courier_Key", "Courier", "api.courier.com", "COURIER_AUTH_TOKEN", "pk_prod", "_", 43, "B64URL", "High"),
    ("09", "Knock_Key", "Knock", "api.knock.app", "KNOCK_API_KEY", "sk_", "", 40, "B64URL", "High"),
    ("09", "Pipedrive_Token", "Pipedrive", "*.pipedrive.com", "PIPEDRIVE_API_TOKEN", "", "", 40, "HEX", "High"),
    ("09", "ActiveCampaign_Key", "ActiveCampaign", "*.api-us1.com", "ACTIVECAMPAIGN_API_KEY", "", "", 64, "HEX", "High"),
    ("09", "Freshdesk_Key", "Freshdesk", "*.freshdesk.com", "FRESHDESK_API_KEY", "", "", 20, "ALNUM", "High"),
    ("09", "Close_Key", "Close", "api.close.com", "CLOSE_API_KEY", "api", "_", 40, "ALNUM", "High"),
    ("09", "Crisp_Key", "Crisp", "api.crisp.chat", "CRISP_KEY", "", "", 0, "UUID", "Medium"),
    ("09", "NCloud_SENS_Access_Key", "Naver Cloud", "sens.apigw.ntruss.com", "SENS_ACCESS_KEY", "ncp_iam_BPAMKR", "", 20, "ALNUM", "High"),
    # --- 10 observability / cdn ---
    ("10", "Axiom_Token", "Axiom", "api.axiom.co", "AXIOM_TOKEN", "xaat", "-", 36, "B64URL", "High"),
    ("10", "BetterStack_Token", "Better Stack", "logs.betterstack.com", "LOGTAIL_TOKEN", "", "", 32, "ALNUM", "High"),
    ("10", "Checkly_Key", "Checkly", "api.checklyhq.com", "CHECKLY_API_KEY", "cu", "_", 32, "HEX", "High"),
    ("10", "Lightstep_Token", "Lightstep", "api.lightstep.com", "LIGHTSTEP_ACCESS_TOKEN", "", "", 44, "B64URL", "High"),
    ("10", "Bunny_Key", "Bunny.net", "api.bunny.net", "BUNNY_API_KEY", "", "", 0, "UUID", "High"),
    ("10", "KeyCDN_Key", "KeyCDN", "api.keycdn.com", "KEYCDN_API_KEY", "", "", 40, "ALNUM", "High"),
    ("10", "Gcore_Token", "Gcore", "api.gcore.com", "GCORE_API_TOKEN", "", "", 64, "HEX", "High"),
    ("10", "UptimeRobot_Key", "UptimeRobot", "api.uptimerobot.com", "UPTIMEROBOT_API_KEY", "u", "", 40, "ALNUM", "Medium"),
    ("10", "Cronitor_Key", "Cronitor", "cronitor.io", "CRONITOR_API_KEY", "", "", 32, "HEX", "Medium"),
    ("10", "Statuspage_Key", "Statuspage", "api.statuspage.io", "STATUSPAGE_API_KEY", "", "", 0, "UUID", "Medium"),
]


def populate(B):
    E = B.E; pfx = B.pfx
    AL = {"ALNUM": E.ALNUM, "HEX": E.HEX, "B64URL": E.B64URL}
    for cat, sub, vendor, host, env, prefix, sep, n, alpha, sev in T:
        if alpha in ("JWT", "UUID", "FALPAIR"):
            # structural formats: synthesize an explicit value + regex
            if alpha == "JWT":
                val = E.jwt("s3:" + sub); rx = r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
                pre = (prefix + sep) if prefix else ""
                val = pre + val
                if pre:
                    rx = re_escape(pre) + rx.lstrip("\\b")
            elif alpha == "UUID":
                val = E.uuid("s3:" + sub); rx = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
            else:  # FALPAIR  key_id:key_secret
                val = "%s:%s" % (E.uuid("s3fa:" + sub), E.d("s3fs:" + sub).chars(32, E.HEX))
                rx = r"\b[0-9a-f-]{36}:[0-9a-f]{32}\b"
            _addraw(B, cat, sub, vendor, host, env, val, rx, sev)
            continue
        pfx(cat, sub, vendor, "scanner catalog / vendor docs (discovery)", host, env, prefix, n, alph=AL[alpha],
            sep=sep, sev=sev, ctx=B._auto_ctx(len(B.ROWS) % 8),
            var=env, neg="envref")


def re_escape(s):
    import re
    return re.escape(s)


def _addraw(B, cat, sub, vendor, host, env, val, rx, sev):
    E = B.E
    ctx = B._auto_ctx(len(B.ROWS) % 8)
    from v3_render import RENDER
    neg = "${" + env + "}"
    B.add(cat, sub, "scanner catalog / vendor docs (discovery)",
          f"{vendor}의 {sub.split('_',1)[-1].replace('_',' ')} 자격증명. {host}에 접근한다.",
          host, f"{env}, {vendor}", rx, val, neg, sev, ctx=ctx, var=env,
          guide=f"{vendor} 토큰의 구조(위 정규식)로 형식을 확정한다. Hard Negative인 `${{{env}}}` 같은 환경변수 참조는 값이 아니므로 "
                f"마스킹하지 않도록 학습한다.")
