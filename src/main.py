import sys
import logging
from pathlib import Path
from datetime import datetime

# Bu sətir olmadan "python src/main.py" kök qovluqdan işə salınanda
# "No module named 'scrape'" xətası verə bilər.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrape import run_scraper
from bronze_to_silver import bronze_to_silver
from silver_to_gold import silver_to_gold

# --- Loglama qurulumu ---
# Task Scheduler-də hər saat işə düşəndə terminal görünmür,
# ona görə nəticələri fayla yazmaq VACİBDİR.
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),  # terminalda da görünsün (əl ilə işə salanda)
    ],
)


def run():
    start = datetime.now()
    logging.info("=" * 50)
    logging.info("Pipeline başladı")

    try:
        logging.info("Addım 1/3: Scraping başlayır...")
        bronze_path = run_scraper(max_items=2000)
        logging.info(f"Scraping bitdi -> {bronze_path}")

        logging.info("Addım 2/3: Bronze -> Silver...")
        silver_path = bronze_to_silver()
        logging.info(f"Silver hazır -> {silver_path}")

        logging.info("Addım 3/3: Silver -> Gold...")
        silver_to_gold()
        logging.info("Gold hazır")

        duration = (datetime.now() - start).total_seconds()
        logging.info(f"Pipeline UĞURLA tamamlandı. Müddət: {duration:.1f} saniyə")

    except Exception as e:
        logging.error(f"Pipeline XƏTA ilə dayandı: {e}", exc_info=True)
        # Xəta olsa belə skript "sükutla" bitməsin — Task Scheduler-in
        # bunu uğursuz run kimi qeyd etməsi üçün.
        sys.exit(1)


if __name__ == "__main__":
    run()