"""Whitelisted RSS feeds — mental-health news and health guides."""

from app.crawl.models import CrawlFeed

CRAWL_FEEDS: list[CrawlFeed] = [
    # International / official
    CrawlFeed(
        feed_id="guardian_mental_health",
        url="https://www.theguardian.com/society/mental-health/rss",
        publisher="The Guardian",
        language="en",
        trust_tier="curated",
        content_type="news_article",
        country="UK",
    ),
    CrawlFeed(
        feed_id="sciencedaily_mental_health",
        url="https://www.sciencedaily.com/rss/mind_brain/mental_health.xml",
        publisher="ScienceDaily",
        language="en",
        trust_tier="curated",
        content_type="news_article",
        country="US",
    ),
    CrawlFeed(
        feed_id="medlineplus_new",
        url="https://medlineplus.gov/groupfeeds/new.xml",
        publisher="MedlinePlus (NIH)",
        language="en",
        trust_tier="official",
        content_type="health_guide",
        country="US",
    ),
    CrawlFeed(
        feed_id="cdc_mental_health",
        url="https://tools.cdc.gov/api/v2/resources/media/132608.rss",
        publisher="CDC",
        language="en",
        trust_tier="official",
        content_type="news_article",
        country="US",
    ),
    # Vietnam
    CrawlFeed(
        feed_id="vnexpress_suc_khoe",
        url="https://vnexpress.net/rss/suc-khoe.rss",
        publisher="VnExpress Sức khỏe",
        language="vi",
        trust_tier="curated",
        content_type="news_article",
        country="VN",
    ),
    CrawlFeed(
        feed_id="thanhnien_suc_khoe",
        url="https://thanhnien.vn/rss/suc-khoe.rss",
        publisher="Thanh Niên Sức khỏe",
        language="vi",
        trust_tier="curated",
        content_type="news_article",
        country="VN",
    ),
    CrawlFeed(
        feed_id="suckhoedoisong_home",
        url="https://suckhoedoisong.vn/rss/home.rss",
        publisher="Sức khỏe & Đời sống",
        language="vi",
        trust_tier="curated",
        content_type="news_article",
        country="VN",
    ),
]
