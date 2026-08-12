import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator, TextInput } from 'react-native';
import { fetchKnowledgeDocuments, KnowledgeDoc } from '../api';

const NAVY = '#0b1740';
const BLUE = '#2f5bff';
const MUTED = '#5b6478';
const BORDER = '#ece9fb';
const BG = '#f7f6fd';

export default function KnowledgeBaseScreen({ navigation }: any) {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');

  useEffect(() => {
    fetchKnowledgeDocuments().then(setDocs).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const filtered = query.trim()
    ? docs.filter(d => d.content.toLowerCase().includes(query.toLowerCase()) || d.title.toLowerCase().includes(query.toLowerCase()))
    : docs;

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={12}>
          <Text style={styles.back}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Knowledge Base</Text>
        <View style={{ width: 44 }} />
      </View>

      <View style={styles.searchWrap}>
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search what Sonorus knows…"
          placeholderTextColor="#a3aabf"
        />
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, paddingTop: 12, paddingBottom: 48 }}>
        {loading && <ActivityIndicator color={BLUE} style={{ marginTop: 30 }} />}
        {!loading && filtered.length === 0 && (
          <Text style={styles.empty}>{query ? 'Nothing matches that search.' : 'No knowledge base content yet.'}</Text>
        )}
        {filtered.map(d => (
          <View key={d.id} style={styles.card}>
            {d.category && (
              <View style={styles.categoryPill}>
                <Text style={styles.categoryText}>{d.category}</Text>
              </View>
            )}
            <Text style={styles.content}>{d.content}</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 58, paddingBottom: 12, paddingHorizontal: 20 },
  back: { color: BLUE, fontWeight: '700', fontSize: 15, width: 44 },
  headerTitle: { color: NAVY, fontWeight: '800', fontSize: 16 },
  searchWrap: { paddingHorizontal: 20 },
  searchInput: { borderWidth: 1, borderColor: BORDER, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: NAVY, backgroundColor: BG },
  empty: { color: MUTED, textAlign: 'center', marginTop: 30, fontSize: 13 },
  card: { backgroundColor: BG, borderRadius: 16, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: BORDER },
  categoryPill: { alignSelf: 'flex-start', backgroundColor: 'rgba(47,91,255,0.1)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20, marginBottom: 10 },
  categoryText: { color: BLUE, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  content: { color: NAVY, fontSize: 14, lineHeight: 20 },
});
