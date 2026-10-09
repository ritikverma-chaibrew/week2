// Canned stories for the demo page and the empty-gallery fallback. Photos: a park bench, a lamp post and a pigeon.
// Written the way the app writes: short sentences and easy words, like a children's picture book.
const svg = (sky, hill, accent, shape) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient></defs><rect width="400" height="300" fill="url(#s)"/><circle cx="320" cy="60" r="30" fill="${accent}" opacity=".85"/><path d="M0 210 Q110 150 220 205 T400 190 V300 H0Z" fill="${hill}"/>${shape}</svg>`;
const bench = '<rect x="90" y="180" width="110" height="10" fill="#6b4226"/><rect x="95" y="160" width="100" height="8" fill="#8a5a33"/><rect x="100" y="190" width="8" height="30" fill="#4a2c17"/><rect x="182" y="190" width="8" height="30" fill="#4a2c17"/>';
const lamp = '<rect x="268" y="100" width="7" height="125" fill="#222"/><circle cx="271" cy="95" r="14" fill="#ffe27a"/>';
const pigeon = '<ellipse cx="150" cy="168" rx="20" ry="13" fill="#8d99ae"/><circle cx="168" cy="158" r="8" fill="#8d99ae"/><polygon points="176,158 186,161 176,164" fill="#f4a261"/>';

export const DEMO = {
  funny: {
    kind: "story",
    title: "Gus and the Big Bench",
    genre: "funny",
    objects: ["lamp post", "park bench", "pigeon"],
    text: `Gus the pigeon had a big plan. He wanted the best bench in the park. It was Bench Seven. It had shade in the morning and sun in the afternoon.

"Today, this bench is mine," said Gus. He puffed up his chest. He looked very proud.

The old lamp post saw him. The lamp post loved to talk. "Hello, Gus!" it hummed. "Why are you wearing a sign?"

Gus did have a sign. It was too big for him. It said, "NO DOGS. NO SQUIRRELS." He wobbled like a tiny walking door.

"This is my country now," said Gus. "I call it Gusland!" Three little sparrows clapped. One crumb did not clap, because it was a crumb.

The lamp post told Doug the squirrel. Doug was the park helper. He wore a tiny hat that he had found. He ran up to the bench and looked at the sign.

"Gus," said Doug, "you cannot own a bench."

"But Gusland has rules!" said Gus. He showed a paper. It was an old napkin with scribbles on it.

Doug read the napkin twice. Then he laughed. "All right," he said. "Gusland can stay. But everyone must share. And the rent is one bread crumb."

"Deal!" said Gus. He did a happy dance.

Now, if you sit on Bench Seven, a pigeon may say hello. Just give him a crumb. He will smile, and so will you.`,
    scenes: [
      { caption: "Gus has a big plan", svg: svg(["#9ad7ff", "#e8f7ff"], "#7bc86c", "#ffd166", bench + pigeon) },
      { caption: "The lamp post tells Doug", svg: svg(["#ffd6a5", "#fff1d6"], "#6fbf73", "#ff9f1c", lamp + pigeon) },
      { caption: "Welcome to Gusland", svg: svg(["#b8f2e6", "#e9fff9"], "#5fb36a", "#ffd166", bench) },
    ],
  },
  horror: {
    kind: "story",
    title: "The Bench That Hummed",
    genre: "horror",
    objects: ["lamp post", "park bench", "pigeon"],
    text: `Mia walked in the park at night. The sky was dark and blue. The lamp post gave a soft, yellow light.

She heard a sound. "Hmmmm. Hmmmm." It was low and slow. Mia stopped. Her heart went thump, thump.

"Who is there?" she asked. Nobody said a word. But the sound did not stop.

She looked at the old green bench. A grey pigeon sat on it. Its eyes were round and bright. It did not move at all.

"Is that you?" Mia whispered. The pigeon tilted its head. The lamp post flickered once, twice. Mia took one small step. Then another.

The humming grew louder. Mia held her breath. She was a little bit scared, but she was brave too.

Then the lamp light flickered again. Mia saw something small under the bench. It was a tiny, shaking baby pigeon. It had lost its mama.

"Oh!" said Mia. "You are only scared, like me."

The big pigeon was not scary at all. It had been humming a song to keep its baby calm. And the old lamp post had been shining to keep them both safe.

Mia picked up the baby gently. She put it under its mama's soft wing. The humming turned into a happy coo.

"Good night," said Mia. She smiled all the way home. The night was not scary any more.`,
    scenes: [
      { caption: "A low, slow hum", svg: svg(["#2b2d42", "#4a4e69"], "#1b2a1e", "#cfd8dc", lamp) },
      { caption: "Two bright, round eyes", svg: svg(["#1d1b2f", "#3a2f55"], "#142018", "#9d8cc2", bench + pigeon) },
      { caption: "The scary sound was a song", svg: svg(["#0b0b12", "#1c1a2b"], "#0e1a12", "#6c5b7b", bench) },
    ],
  },
  suspense: {
    kind: "story",
    title: "The Case of the Missing Crumbs",
    genre: "suspense",
    objects: ["lamp post", "park bench", "pigeon"],
    text: `Every morning, Sam left a bag of crumbs on Bench Seven. Every morning, a happy pigeon ate them. But today the bag was empty. The crumbs were gone!

"Someone took them," said Sam. "I must find out who."

He looked at the bench. He saw a tiny footprint in the dust. It was not a pigeon's foot. It was too small and too round.

Sam followed the footprints. They went past the old lamp post. Then they went across the grass. The trail stopped at a big, hollow log.

Sam sat very still. He did not make a sound. Soon he heard a little noise. Rustle, rustle, nibble, nibble.

A small nose poked out of the log. Then came a pair of tiny ears. It was a baby hedgehog! It had a crumb on its chin.

"You are the crumb thief," Sam said softly.

The hedgehog froze. Its eyes were big and sad. "I was so hungry," it seemed to say.

Sam smiled. "You do not have to take them," he said. "You can ask."

Just then, the pigeon landed next to them. It cooed and pushed a crumb with its beak. It wanted to share too.

From that day on, Sam left two bags of crumbs. One was for the pigeon. One was for his new friend. And the lamp post shone over them all.`,
    scenes: [
      { caption: "The crumbs are gone!", svg: svg(["#355c7d", "#6c91a8"], "#2f5d3a", "#f6e58d", bench) },
      { caption: "A trail past the lamp post", svg: svg(["#264653", "#4f7f8a"], "#25472f", "#e9c46a", lamp + pigeon) },
      { caption: "The pigeon wants to share", svg: svg(["#3d405b", "#6f7396"], "#233d2a", "#f2cc8f", pigeon) },
    ],
  },
};
