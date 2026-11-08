// Interface text in three languages. Keys must match across en / uz / ru.
window.I18N = {
  en: {
    htmlLang: "en",
    tagline: "Every AI model, tool, repo and course in one place",
    lede: "Find chat models, coding assistants, open-source GitHub projects, free courses and useful websites. Search works in English, Uzbek and Russian.",
    searchLabel: "Search",
    searchPh: "Search models, tools, repos, courses…",
    cats: { all: "All", model: "Models", tool: "Tools", repo: "GitHub repos", learn: "Learning", site: "Websites" },
    priceAll: "Any price",
    price: { free: "Free", freemium: "Free plan", paid: "Paid", open: "Open source" },
    visit: "Visit",
    count: (n) => n === 1 ? "1 resource" : n + " resources",
    empty: (q) => q ? "Nothing found for “" + q + "”. Try a shorter word or another category." : "Nothing in this category yet.",
    footer: "Know a resource that belongs here? Add it to <code>data.js</code> and open a pull request. Links lead to the official sites.",
    tags: {
      chat: "Chat", code: "Code", image: "Images", video: "Video", audio: "Audio", local: "Runs locally",
      agents: "Agents", research: "Research", rag: "RAG", ranking: "Rankings", api: "API",
      beginner: "Beginners", llm: "LLM", search: "Search", datasets: "Datasets", math: "Math", ui: "Web UI"
    }
  },
  uz: {
    htmlLang: "uz",
    tagline: "Barcha sunʼiy intellekt modellari, vositalari va kurslari bir joyda",
    lede: "Chat modellari, dasturlash yordamchilari, ochiq kodli GitHub loyihalari, bepul kurslar va foydali saytlarni toping. Qidiruv oʻzbek, ingliz va rus tillarida ishlaydi.",
    searchLabel: "Qidiruv",
    searchPh: "Model, vosita, repozitoriy yoki kurs qidiring…",
    cats: { all: "Hammasi", model: "Modellar", tool: "Vositalar", repo: "GitHub repolar", learn: "Oʻrganish", site: "Saytlar" },
    priceAll: "Har qanday narx",
    price: { free: "Bepul", freemium: "Bepul tarif bor", paid: "Pullik", open: "Ochiq kodli" },
    visit: "Ochish",
    count: (n) => n + " ta manba",
    empty: (q) => q ? "“" + q + "” boʻyicha hech narsa topilmadi. Qisqaroq soʻz yoki boshqa boʻlimni sinab koʻring." : "Bu boʻlimda hozircha hech narsa yoʻq.",
    footer: "Bu yerda boʻlishi kerak boʻlgan manbani bilasizmi? Uni <code>data.js</code> fayliga qoʻshing va pull request oching. Havolalar rasmiy saytlarga olib boradi.",
    tags: {
      chat: "Chat", code: "Dasturlash", image: "Rasm", video: "Video", audio: "Ovoz", local: "Kompyuterda ishlaydi",
      agents: "Agentlar", research: "Tadqiqot", rag: "RAG", ranking: "Reyting", api: "API",
      beginner: "Boshlovchilar uchun", llm: "LLM", search: "Qidiruv", datasets: "Datasetlar", math: "Matematika", ui: "Veb interfeys"
    }
  },
  ru: {
    htmlLang: "ru",
    tagline: "Все ИИ-модели, инструменты, репозитории и курсы в одном месте",
    lede: "Чат-модели, помощники для программирования, open-source проекты на GitHub, бесплатные курсы и полезные сайты. Поиск работает на русском, узбекском и английском.",
    searchLabel: "Поиск",
    searchPh: "Ищите модели, инструменты, репозитории, курсы…",
    cats: { all: "Все", model: "Модели", tool: "Инструменты", repo: "Репозитории", learn: "Обучение", site: "Сайты" },
    priceAll: "Любая цена",
    price: { free: "Бесплатно", freemium: "Есть бесплатный план", paid: "Платно", open: "Открытый код" },
    visit: "Открыть",
    count: (n) => "Ресурсов: " + n,
    empty: (q) => q ? "По запросу «" + q + "» ничего не найдено. Попробуйте слово короче или другой раздел." : "В этом разделе пока пусто.",
    footer: "Знаете полезный ресурс? Добавьте его в <code>data.js</code> и откройте pull request. Ссылки ведут на официальные сайты.",
    tags: {
      chat: "Чат", code: "Код", image: "Изображения", video: "Видео", audio: "Аудио", local: "Работает локально",
      agents: "Агенты", research: "Исследования", rag: "RAG", ranking: "Рейтинги", api: "API",
      beginner: "Для новичков", llm: "LLM", search: "Поиск", datasets: "Датасеты", math: "Математика", ui: "Веб-интерфейс"
    }
  }
};
