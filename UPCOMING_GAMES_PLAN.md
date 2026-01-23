# Upcoming Games Feature Implementation Plan

The user wants to add a section for "Upcoming Games" specifically for Nintendo Switch. We will utilize the IGDB API (which is already configured in the system) to fetch future releases.

## User Review Required

> [!IMPORTANT]
> **API Dependency**: This feature requires a valid **IGDB Client ID** and **Client Secret** to be configured in the settings. If they are missing, the section will show a reminder to configure them.

> [!NOTE]
> **Caching**: To improve performance and respect IGDB rate limits, the upcoming games data will be cached for 24 hours.

## Proposed Changes

### [Backend] API and Services

#### [MODIFY] [rating_service.py](file:///Users/fernandosouza/Documents/Projetos/MyFoil/app/services/rating_service.py)
- Add `get_upcoming_games(limit=20)` method to `IGDBClient`.
- Query: `fields name, first_release_date, cover.url, summary, genres.name; where platforms = (130) & first_release_date > CURRENT_TIMESTAMP; sort first_release_date asc; limit 20;`

#### [NEW] [upcoming.py](file:///Users/fernandosouza/Documents/Projetos/MyFoil/app/routes/upcoming.py)
- Create new blueprint for upcoming games.
- Endpoint `GET /api/upcoming` that returns the list of future releases.
- Implements a simple file-based cache (`upcoming_cache.json`).

#### [MODIFY] [app.py](file:///Users/fernandosouza/Documents/Projetos/MyFoil/app/app.py)
- Register `upcoming_bp`.
- Add route for `/upcoming` page.

---

### [Frontend] UI and Templates

#### [NEW] [upcoming.html](file:///Users/fernandosouza/Documents/Projetos/MyFoil/app/templates/upcoming.html)
- New page template using the existing design system (Bulma + custom glassmorphism).
- Displays a grid of cards for each upcoming game.

#### [NEW] [upcoming.js](file:///Users/fernandosouza/Documents/Projetos/MyFoil/app/static/js/upcoming.js)
- JS logic to fetch and render the games.
- Handles empty states and loading indicators.

#### [MODIFY] [nav.html](file:///Users/fernandosouza/Documents/Projetos/MyFoil/app/templates/nav.html)
- Add "Próximos" link to the top navigation bar.

---

## Verification Plan

### Automated Tests
- N/A (Mostly UI and external API integration)

### Manual Verification
1.  Navigate to the new "Próximos" page.
2.  Verify that games from IGDB are displayed with correct release dates.
3.  Check if the "Configure API" message appears if keys are missing.
4.  Verify that the "Wishlist" button (if implemented) works for upcoming titles.
