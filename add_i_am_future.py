import sys
import os
from datetime import datetime

# Ensure we can import from app
sys.path.append('/app')

from app import app
from db import db, Titles, TitleDBCache

game_data = {
    "70010000094992": {
        "bannerUrl": "https://img-eshop.cdn.nintendo.net/i/7e120016c339e5d86efa094e4cda4403228042e932b8abfcfa14716cd6d3e0b8.jpg",
        "category": [
            "Simulação",
            "RPG"
        ],
        "description": "CONSTRUA A BASE ACONCHEGANTE DOS SEUS SONHOS NO TELHADO\n\nComece do zero em um telhado abandonado e construa, decore e amplie o acampamento mais confortável de todos! Desbloqueie novas estruturas e móveis, monte redes elétricas e organize sua nova vida. Relaxe, construa e passeie por aí: o mundo é seu, literalmente! \n\nDEFINA SEU PERSONAGEM\n\nJogue como Robin ou Chris e defina seu protagonista para refletir a imagem que você tem da última pessoa viva na Terra!\n\nPROCURE RELÍQUIAS DO MUNDO ANTIGO PARA FABRICAR NOVOS APARELHOS\n\nEncontre artefatos de uma era passada, como chaleiras, televisores ou micro-ondas e desmonte-os com a gratificante mecânica de desmonte para conseguir os recursos necessários para seu próximo projeto!\n\nCONTRATE UMA EQUIPE DE LACAIOS ROBÓTICOS FOFINHOS\n\nAutomatize as tarefas do acampamento com a ajuda de robôr fofinhos! Monte uma equipe de lacaios robóticos, dê ordens e recompense-os com um relaxante banho de recarga!\n\nEXPLORE UM MUNDO MISTERIOSO\n\nEnvie expedições de drones de reconhecimento pela megalópole afundada. Descubra novos locais, recupere itens valiosos e descubra a verdade por trás do fim do mundo, um passo de cada vez.\n\nFAÇA AMIZADES INCRÍVEIS\n\nO fato de você ser a última pessoa viva na Terra não significa que estará sem amigos! Encontre os excêntricos habitantes robóticos desse novo mundo, como a geladeira Earl ou a bombástica Bárbara e aprofunde sua amizade com eles.\n\nPROTEJA SUA BASE CONTRA PESTES\n\nAlém de muito amor, seu acampamento também precisa de proteção. Impeça as pestes mutantes de destruir suas plantações ou a rede elétrica!\n",
        "developer": None,
        "frontBoxArt": None,
        "iconUrl": "https://img-eshop.cdn.nintendo.net/i/aa5ae5aa7995e963fa90e5c88a26018dbda7fd540d78b2dd864c923e58740bd4.jpg",
        "id": "0100A10022CC2000",
        "intro": "O mundo acabou? É hora de construir o cantinho que você sonhou e fazer amizades.",
        "isDemo": False,
        "key": None,
        "languages": [
            "ja",
            "en",
            "pt",
            "es",
            "fr",
            "de",
            "ru",
            "ko",
            "zh"
        ],
        "name": "I Am Future: Cozy Apocalypse Survival",
        "nsuId": 70010000094992,
        "numberOfPlayers": 1,
        "publisher": "tinyBuild Games",
        "rating": 0,
        "ratingContent": [
            "Linguagem Imprópria"
        ],
        "region": None,
        "releaseDate": 20260108,
        "rightsId": None,
        "screenshots": [
            "https://img-eshop.cdn.nintendo.net/i/7873eb9f99015337c37a941d712415a361d06d7a6498b027d655f969c5c13cd2.jpg",
            "https://img-eshop.cdn.nintendo.net/i/b2778ab3971edb8bd10e19e1d2df8a3de79178dd1d7cdf5e7f8b867d0b260a70.jpg",
            "https://img-eshop.cdn.nintendo.net/i/350e5df57bb175d26f328b3904cc4c5b407d72dd245dce70fbe33d1b766917ac.jpg",
            "https://img-eshop.cdn.nintendo.net/i/71b3d74954616be98e0440d0b1f6dad755c1c94a5a75dae383c33e3026760df3.jpg",
            "https://img-eshop.cdn.nintendo.net/i/2f6e3163a14c5f147e128ff66c28a5bd6650c7e71477cf4a221c9220e626ea3c.jpg",
            "https://img-eshop.cdn.nintendo.net/i/b2778ab3971edb8bd10e19e1d2df8a3de79178dd1d7cdf5e7f8b867d0b260a70.jpg"
        ],
        "size": 780140544,
        "version": None
    }
}

title_id = "0100A10022CC2000"
info = game_data["70010000094992"]

with app.app_context():
    # 1. Update TitleDBCache (for global recognition)
    cache_entry = TitleDBCache.query.filter_by(title_id=title_id).first()
    if not cache_entry:
        print(f"Adding {title_id} to TitleDBCache...")
        cache_entry = TitleDBCache(title_id=title_id, data=info, source="manual_injection")
        db.session.add(cache_entry)
    else:
        print(f"Updating {title_id} in TitleDBCache...")
        cache_entry.data = info
        cache_entry.source = "manual_injection"

    # 2. Update Titles table (for permanent metadata)
    title_record = Titles.query.filter_by(title_id=title_id).first()
    if not title_record:
        print(f"Creating Titles record for {title_id}...")
        title_record = Titles(title_id=title_id)
        db.session.add(title_record)
    
    title_record.name = info.get("name")
    title_record.description = info.get("description")
    title_record.publisher = info.get("publisher")
    title_record.icon_url = info.get("iconUrl")
    title_record.banner_url = info.get("bannerUrl")
    title_record.release_date = str(info.get("releaseDate"))
    title_record.size = info.get("size")
    title_record.nsuid = str(info.get("nsuId"))
    title_record.category = ",".join(info.get("category", []))
    title_record.screenshots_json = info.get("screenshots", [])
    title_record.is_custom = True
    title_record.last_updated = datetime.now()

    db.session.commit()
    print("Optimization: Done! Game successfully added to local database.")
