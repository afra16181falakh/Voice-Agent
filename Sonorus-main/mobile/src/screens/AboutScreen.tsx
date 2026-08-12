import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

const NAVY = '#0b1740';
const BLUE = '#2f5bff';
const BLUE_LIGHT = '#7c9bff';
const VIOLET = '#7c3aed';
const MUTED = '#5b6478';
const BORDER = '#ece9fb';

const MODES = [
  {
    title: 'Sonorus Companion',
    tag: 'YOUR EVERYDAY CONVERSATION',
    colors: [BLUE_LIGHT, BLUE],
    body: "Inbound, warm, and emotionally aware — a conversation that remembers context and answers real questions, grounded in your own knowledge base.",
    features: [
      'English + Hindi, natural code-switching',
      'Emotion-aware, human-length replies',
      'Answers grounded in your knowledge base',
      'Hands off to a human when it should',
    ],
  },
  {
    title: 'Sonorus Outbound',
    tag: 'AUTOMATED OUTREACH',
    colors: ['#c4b5fd', VIOLET],
    body: "Sonorus places the call and speaks first — grounded in the real account it's calling about, from the opening line to the close.",
    features: [
      'Agent speaks first, no script-reading',
      'Grounded in the specific customer record',
      'Negotiates payment dates, not just states facts',
      'Never pressures — escalates hardship to a human',
    ],
  },
];

const HOW_IT_WORKS = [
  { step: '01', title: 'Pick the scenario', body: 'A warm personal conversation, or an outbound reminder call.' },
  { step: '02', title: 'The agent listens and responds', body: 'Speech is transcribed, reasoned over, and answered in natural, spoken-length sentences.' },
  { step: '03', title: 'It escalates when it should', body: 'A dispute, real distress, an explicit ask — the agent hands off cleanly instead of guessing.' },
  { step: '04', title: 'You see everything', body: 'Live transcript and outcome, logged for review afterward.' },
];

const FAQS = [
  { q: 'What languages does it support?', a: 'English and Hindi, including natural code-switching mid-conversation.' },
  { q: "Does it make things up if it doesn't know an answer?", a: 'No — replies are grounded in retrieved content. If nothing relevant is found, it says so rather than guessing.' },
  { q: 'What happens when a caller is upset or wants a human?', a: 'The agent recognizes hardship, disputes, and explicit requests for a person, and hands off with context intact.' },
];

export default function AboutScreen({ navigation }: any) {
  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingBottom: 48 }}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={12}>
          <Text style={styles.back}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>About Sonorus</Text>
        <View style={{ width: 44 }} />
      </View>

      <View style={styles.section}>
        <Text style={styles.eyebrow}>TWO PURPOSE-BUILT MODES</Text>
        {MODES.map(m => (
          <LinearGradient key={m.title} colors={m.colors as any} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.modeCard}>
            <Text style={styles.modeTag}>{m.tag}</Text>
            <Text style={styles.modeTitle}>{m.title}</Text>
            <Text style={styles.modeBody}>{m.body}</Text>
            {m.features.map(f => (
              <View key={f} style={styles.featureRow}>
                <Text style={styles.featureCheck}>✓</Text>
                <Text style={styles.featureText}>{f}</Text>
              </View>
            ))}
          </LinearGradient>
        ))}
      </View>

      <View style={styles.section}>
        <Text style={styles.eyebrow}>HOW IT WORKS</Text>
        {HOW_IT_WORKS.map(s => (
          <View key={s.step} style={styles.howCard}>
            <Text style={styles.howStep}>{s.step}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.howTitle}>{s.title}</Text>
              <Text style={styles.howBody}>{s.body}</Text>
            </View>
          </View>
        ))}
      </View>

      <View style={styles.section}>
        <Text style={styles.eyebrow}>GOOD TO KNOW</Text>
        {FAQS.map(item => (
          <View key={item.q} style={styles.faqItem}>
            <Text style={styles.faqQ}>{item.q}</Text>
            <Text style={styles.faqA}>{item.a}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 58, paddingBottom: 12, paddingHorizontal: 20 },
  back: { color: BLUE, fontWeight: '700', fontSize: 15, width: 44 },
  headerTitle: { color: NAVY, fontWeight: '800', fontSize: 16 },

  section: { paddingHorizontal: 20, marginTop: 20 },
  eyebrow: { color: BLUE, fontWeight: '800', fontSize: 11, letterSpacing: 1, marginBottom: 14 },

  modeCard: { borderRadius: 22, padding: 20, marginBottom: 14 },
  modeTag: { color: 'rgba(255,255,255,0.85)', fontWeight: '800', fontSize: 10, letterSpacing: 0.5 },
  modeTitle: { color: '#fff', fontWeight: '800', fontSize: 19, marginTop: 6 },
  modeBody: { color: 'rgba(255,255,255,0.9)', fontSize: 13, marginTop: 8, lineHeight: 19 },
  featureRow: { flexDirection: 'row', alignItems: 'flex-start', marginTop: 8 },
  featureCheck: { color: '#fff', fontWeight: '800', marginRight: 8, fontSize: 13 },
  featureText: { color: '#fff', fontSize: 12.5, flex: 1, lineHeight: 18 },

  howCard: { flexDirection: 'row', backgroundColor: '#f7f6fd', borderWidth: 1, borderColor: BORDER, borderRadius: 16, padding: 16, marginBottom: 10, gap: 14 },
  howStep: { color: BLUE, fontWeight: '800', fontSize: 14 },
  howTitle: { color: NAVY, fontWeight: '800', fontSize: 14.5 },
  howBody: { color: MUTED, fontSize: 12.5, marginTop: 4, lineHeight: 18 },

  faqItem: { backgroundColor: '#fff', borderRadius: 14, borderWidth: 1, borderColor: BORDER, padding: 16, marginBottom: 10 },
  faqQ: { color: NAVY, fontWeight: '700', fontSize: 14 },
  faqA: { color: MUTED, fontSize: 12.5, marginTop: 8, lineHeight: 18 },
});
