import { Page, Section, Text } from 'grok/canvas';
export default function Workshop({revised = false}: {revised?: boolean}) {
 return <Page title="A little room to make." summary="A Saturday workshop, taking shape.">
  <Section><Text>A quiet afternoon of paper, color, and good company. Make something small to take home.</Text></Section>
  <Section><Text>Meet at the studio at two. Materials and a warm drink are included.</Text></Section>
  <Section><Text>{revised ? 'Eight places, one shared table. Beginners are welcome.' : 'A shared table. Beginners are welcome.'}</Text></Section>
  {revised && <Section><Text>Choose a favorite piece for a small, shared display before heading home.</Text></Section>}
 </Page>;
}
