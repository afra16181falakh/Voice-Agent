import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { fetchTelemetryOverview, TelemetryOverview } from '../api';

const NAVY = '#0b1740';
const BLUE = '#2f5bff';
const BLUE_LIGHT = '#7c9bff';
const VIOLET = '#7c3aed';
const MUTED = '#5b6478';
const BORDER = '#ece9fb';
const BG = '#f7f6fd';

export default function DashboardScreen({ navigation }: any) {
  const [data, setData] = useState<TelemetryOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTelemetryOverview().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={12}>
          <Text style={styles.back}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Dashboard</Text>
        <View style={{ width: 44 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 48 }}>
        {loading && <ActivityIndicator color={BLUE} style={{ marginTop: 30 }} />}
        {!loading && !data && <Text style={styles.empty}>Couldn't load live metrics right now.</Text>}

        {data && (
          <>
            <LinearGradient colors={[BLUE_LIGHT, BLUE, NAVY]} start={{ x: 0.1, y: 0 }} end={{ x: 1, y: 1 }} style={styles.statusCard}>
              <View style={styles.statusDot} />
              <Text style={styles.statusText}>{data.system_status}</Text>
              <Text style={styles.statusSub}>{data.active_sessions} live session{data.active_sessions === 1 ? '' : 's'} right now</Text>
            </LinearGradient>

            <View style={styles.grid}>
              <StatTile label="Total conversations" value={String(data.total_conversations)} />
              <StatTile label="Success rate" value={`${data.success_rate}%`} />
              <StatTile label="Daily users" value={String(data.daily_users)} />
              <StatTile label="Weekly users" value={String(data.weekly_users)} />
              <StatTile label="Avg. session" value={`${Math.round(data.avg_session_duration_s)}s`} />
              <StatTile label="Avg. reply latency" value={`${Math.round(data.avg_response_latency_ms)}ms`} />
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.tile}>
      <Text style={styles.tileValue}>{value}</Text>
      <Text style={styles.tileLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 58, paddingBottom: 12, paddingHorizontal: 20 },
  back: { color: BLUE, fontWeight: '700', fontSize: 15, width: 44 },
  headerTitle: { color: NAVY, fontWeight: '800', fontSize: 16 },
  empty: { color: MUTED, textAlign: 'center', marginTop: 30, fontSize: 13 },

  statusCard: { borderRadius: 22, padding: 20, marginBottom: 18 },
  statusDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#4ade80' },
  statusText: { color: '#fff', fontWeight: '800', fontSize: 18, marginTop: 10 },
  statusSub: { color: 'rgba(255,255,255,0.8)', fontSize: 12, marginTop: 4 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  tile: { width: '47%', backgroundColor: BG, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: BORDER },
  tileValue: { color: NAVY, fontWeight: '800', fontSize: 20 },
  tileLabel: { color: MUTED, fontSize: 11, marginTop: 6, fontWeight: '600' },
});
