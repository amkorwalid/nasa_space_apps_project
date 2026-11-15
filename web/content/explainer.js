// "How radar sees water" explainer text (Track E). One entry per language; HTML allowed.
export const EXPLAINER = {
  en: {
    title: 'How radar sees water',
    calm: 'Calm water → mirror → DARK',
    rough: 'Rough land → scatter → BRIGHT',
    sections: [
      ['☁ Works through clouds', 'Radar is an <em>active</em> sensor: it sends its own microwave pulses, so it sees the ground day and night, even during the rainy season when reservoirs refill and optical satellites are blind.'],
      ['🌊 Water looks dark', 'Calm water reflects the pulse away like a mirror, so almost nothing comes back: water appears very dark. Land scatters energy back to the satellite and appears brighter.'],
      ['🛰 NISAR every 12 days', "NASA-ISRO's NISAR images each spot about every 12 days. Its long L-band wavelength helps separate open water, flooded vegetation and land. Sentinel-1 (since 2015) gives the long-term baseline."],
      ['📐 From images to status', '<ol><li>An automatic (Otsu) threshold separates dark water from land.</li><li>Terrain (height above the lake) and maximum-extent masks remove false water.</li><li>A monthly majority vote across scenes gives one water map per month.</li><li>The area is compared with the 2015–2024 normal for that month.</li></ol>'],
    ],
    classes: 'Status classes',
    note: 'Surface area is not volume: a reservoir can hold less water than its area suggests. Status is area-based; where official fill rates exist, an area–storage curve converts area to an estimated % full.',
  },
  fr: {
    title: "Comment le radar voit l'eau",
    calm: 'Eau calme → miroir → SOMBRE',
    rough: 'Sol rugueux → diffusion → CLAIR',
    sections: [
      ['☁ Voit à travers les nuages', "Le radar est un capteur <em>actif</em> : il émet ses propres impulsions micro-ondes. Il voit le sol de jour comme de nuit, même pendant la saison des pluies, quand les barrages se remplissent et que les satellites optiques sont aveugles."],
      ["🌊 L'eau apparaît sombre", "L'eau calme renvoie l'impulsion ailleurs, comme un miroir : presque rien ne revient, l'eau apparaît très sombre. Le sol diffuse l'énergie vers le satellite et apparaît plus clair."],
      ['🛰 NISAR tous les 12 jours', "NISAR (NASA-ISRO) observe chaque point environ tous les 12 jours. Sa grande longueur d'onde (bande L) distingue l'eau libre, la végétation inondée et le sol. Sentinel-1 (depuis 2015) fournit la référence de long terme."],
      ["📐 Des images à l'état", "<ol><li>Un seuil automatique (Otsu) sépare l'eau sombre du sol.</li><li>Des masques de relief (hauteur au-dessus du lac) et d'étendue maximale suppriment les fausses détections.</li><li>Un vote majoritaire mensuel donne une carte d'eau par mois.</li><li>La surface est comparée à la normale 2015–2024 du même mois.</li></ol>"],
    ],
    classes: "Classes d'état",
    note: "Surface n'est pas volume : une retenue peut contenir moins d'eau que sa surface ne le suggère. L'état est fondé sur la surface ; là où des taux officiels existent, une courbe surface–volume estime le % de remplissage.",
  },
  ar: {
    title: 'كيف يرى الرادار الماء',
    calm: 'ماء هادئ ← مرآة ← داكن',
    rough: 'أرض خشنة ← تشتّت ← ساطع',
    sections: [
      ['☁ يرى عبر السحب', 'الرادار مستشعر <em>نشِط</em>: يرسل نبضاته الميكروية الخاصة، فيرى الأرض ليلًا ونهارًا، حتى في موسم الأمطار حين تمتلئ السدود وتعجز الأقمار البصرية عن الرؤية.'],
      ['🌊 الماء يبدو داكنًا', 'يعكس الماء الهادئ النبضة بعيدًا كالمرآة، فلا يعود منها شيء تقريبًا ويبدو الماء داكنًا جدًا. أمّا اليابسة فتشتّت الطاقة نحو القمر فتبدو أكثر سطوعًا.'],
      ['🛰 NISAR كل 12 يومًا', 'يصوّر القمر NISAR (ناسا والوكالة الهندية) كل نقطة كل 12 يومًا تقريبًا، وطول موجته (النطاق L) يميّز الماء المكشوف والنبات المغمور واليابسة. ويوفّر Sentinel-1 (منذ 2015) المرجع طويل الأمد.'],
      ['📐 من الصور إلى الحالة', '<ol><li>عتبة تلقائية (Otsu) تفصل الماء الداكن عن اليابسة.</li><li>أقنعة التضاريس والامتداد الأقصى تزيل الكشوف الخاطئة.</li><li>تصويت أغلبية شهري يعطي خريطة ماء واحدة لكل شهر.</li><li>تُقارن المساحة بالمعدل (2015–2024) لنفس الشهر.</li></ol>'],
    ],
    classes: 'فئات الحالة',
    note: 'المساحة ليست الحجم: قد يحتوي السد على ماء أقل مما توحي به مساحته. الحالة مبنية على المساحة، وحيث تتوفر نسب الملء الرسمية يحوّل منحنى المساحة–الحجم المساحة إلى نسبة ملء تقديرية.',
  },
};
