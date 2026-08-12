import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { fetchCallHistory, CallHistoryEntry } from '../api';

const NAVY = '#0b1740';
const BLUE = '#2f5bff';
const VIOLET = '#7c3aed';
const MUTED = '#5b6478';
const BORDER = '#ece9fb';
const BG = '#f7f6fd';

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' · ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function durationLabel(started: string, ended: string | null) {
  if (!ended) return 'In progress';
  const secs = Math.max(0, Math.round((new Date(ended).getTime() - new Date(started).getTime()) / 1000));
  if (secs < 60) return `${secs}s`;
  return `${Math.round(secs / 60)}m`;
}

export default function CallHistoryScreen({ navigation }: any) {
  const [entries, setEntries] = useState<CallHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetchCallHistory().then(setEntries).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={12}>
          <Text style={styles.back}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Call History</Text>
        <View style={{ width: 44 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 48 }}>
        {loading && <ActivityIndicator color={BLUE} style={{ marginTop: 30 }} />}
        {!loading && entries.length === 0 && (
          <Text style={styles.empty}>No calls yet — talk to Sonorus and it'll show up here.</Text>
        )}
        {entries.map(e => {
          const isOpen = expanded === e.session_id;
          const isOutbound = e.call_type === 'loan_reminder';
          return (
            <TouchableOpacity
              key={e.session_id}
              style={styles.card}
              onPress={() => setExpanded(isOpen ? null : e.session_id)}
              activeOpacity={0.8}
            >
              <View style={styles.cardTop}>
                <View style={[styles.typeBadge, { backgroundColor: isOutbound ? 'rgba(124,58,237,0.1)' : 'rgba(47,91,255,0.1)' }]}>
                  <Text style={[styles.typeBadgeText, { color: isOutbound ? VIOLET : BLUE }]}>
                    {isOutbound ? '📞 Outbound' : '💬 Companion'}
                  </Text>
                </View>
                <Text style={styles.duration}>{durationLabel(e.started_at, e.ended_at)}</Text>
              </View>
              <Text style={styles.cardTitle}>{e.customer_name || 'Personal conversation'}</Text>
              <Text style={styles.cardDate}>{formatDate(e.started_at)}</Text>

              {isOpen && (
                <View style={styles.transcriptBox}>
                  {e.transcript.length === 0 && <Text style={styles.transcriptEmpty}>No transcript recorded.</Text>}
                  {e.transcript.map((t, i) => (
                    <View key={i} style={styles.transcriptLine}>
                      <Text style={styles.transcriptSpeaker}>{t.role === 'user' ? 'You' : 'Sonorus'}</Text>
                      <Text style={styles.transcriptText}>{t.text}</Text>
                    </View>
                  ))}
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 58, paddingBottom: 12, paddingHorizontal: 20 },
  back: { color: BLUE, fontWeight: '700', fontSize: 15, width: 44 },
  headerTitle: { color: NAVY, fontWeight: '800', fontSize: 16 },
  empty: { color: MUTED, textAlign: 'center', marginTop: 40, fontSize: 13 },

  card: { backgroundColor: BG, borderRadius: 16, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: BORDER },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  typeBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  typeBadgeText: { fontSize: 11, fontWeight: '800' },
  duration: { color: MUTED, fontSize: 11, fontWeight: '700' },
  cardTitle: { color: NAVY, fontWeight: '800', fontSize: 15, marginTop: 10 },
  cardDate: { color: MUTED, fontSize: 12, marginTop: 3 },

  transcriptBox: { marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: BORDER },
  transcriptEmpty: { color: MUTED, fontSize: 12 },
  transcriptLine: { marginBottom: 10 },
  transcriptSpeaker: { color: MUTED, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', marginBottom: 2 },
  transcriptText: { color: NAVY, fontSize: 13, lineHeight: 18 },
});
