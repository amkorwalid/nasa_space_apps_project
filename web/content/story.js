// Guided story (Track E storyline): national view -> drought low -> Al Massira -> southern drought.
// Each step: what to show (target) + text per language. {placeholders} are filled from the data.
export const STORY = [
  {
    target: { view: 'national', month: 'latest' },
    text: {
      en: ['Morocco from radar', 'SaddSAR follows {n} reservoirs every month with NISAR and Sentinel-1 radar, through clouds. In {month}, their water area is <b>{pct}</b> of normal.'],
      fr: ['Le Maroc vu par radar', 'SaddSAR suit {n} retenues chaque mois avec les radars NISAR et Sentinel-1, à travers les nuages. En {month}, leur surface en eau est à <b>{pct}</b> de la normale.'],
      ar: ['المغرب بعين الرادار', 'يرصد SaddSAR {n} سدًّا كل شهر برادارَي NISAR وSentinel-1 عبر السحب. في {month} بلغت مساحتها المائية <b>{pct}</b> من المعدل.'],
    },
  },
  {
    target: { view: 'national', month: 'lowest' },
    text: {
      en: ['The low point', 'The lowest month on record here is {month}: water area fell to <b>{pct}</b> of normal after years of drought.'],
      fr: ['Le point bas', "Le mois le plus bas de la série est {month} : la surface en eau est tombée à <b>{pct}</b> de la normale après des années de sécheresse."],
      ar: ['أدنى نقطة', 'أدنى شهر في السلسلة هو {month}: انخفضت المساحة المائية إلى <b>{pct}</b> من المعدل بعد سنوات من الجفاف.'],
    },
  },
  {
    target: { reservoir: 'MAR_0001', month: 'latest' },
    text: {
      en: ['Al Massira', "Morocco's second-largest reservoir. In {month} radar measured <b>{area} km²</b> of water, {pct} of normal ({yoy} vs one year earlier). Drag the time slider to watch it change."],
      fr: ['Al Massira', "Deuxième retenue du Maroc. En {month}, le radar mesure <b>{area} km²</b> d'eau, soit {pct} de la normale ({yoy} sur un an). Faites glisser le curseur pour voir l'évolution."],
      ar: ['المسيرة', 'ثاني أكبر سد في المغرب. في {month} قاس الرادار <b>{area} كم²</b> من الماء، أي {pct} من المعدل ({yoy} مقارنة بالسنة السابقة).'],
    },
  },
  {
    target: { reservoir: 'MAR_0002', month: 'latest' },
    text: {
      en: ['Al Wahda, the north', 'The largest dam (3,800 Mm³) in the wetter Sebou basin: {pct} of normal in {month}.'],
      fr: ['Al Wahda, le nord', 'Le plus grand barrage (3 800 Mm³), dans le bassin plus humide du Sebou : {pct} de la normale en {month}.'],
      ar: ['الوحدة، الشمال', 'أكبر سد (3800 مليون م³) في حوض سبو الأكثر رطوبة: {pct} من المعدل في {month}.'],
    },
  },
  {
    target: { reservoir: 'MAR_0004', month: 'latest' },
    text: {
      en: ['Al Mansour Ad Dahbi, the south', 'Near Ouarzazate in the arid Draa basin, recovery is slower: <b>{pct}</b> of normal in {month}. Radar keeps watching where drought still holds.'],
      fr: ['Al Mansour Ad Dahbi, le sud', 'Près de Ouarzazate, dans le bassin aride du Draa, la reprise est plus lente : <b>{pct}</b> de la normale en {month}.'],
      ar: ['المنصور الذهبي، الجنوب', 'قرب ورزازات في حوض درعة الجاف، التعافي أبطأ: <b>{pct}</b> من المعدل في {month}.'],
    },
  },
];
