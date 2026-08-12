import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Animated,
  Easing,
  Pressable,
  Platform,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { fetchLoanCustomers, fetchOverview, LoanCustomer } from '../api';
import { logout, getStoredUser, AuthUser } from '../auth';
import DrawerMenu from '../components/DrawerMenu';

const NAVY = '#0b1740';
const BLUE = '#2f5bff';
const BLUE_LIGHT = '#7c9bff';
const VIOLET = '#7c3aed';
const VIOLET_LIGHT = '#c4b5fd';
const MUTED = '#5b6478';
const BORDER = '#ece9fb';
const BG = '#f7f6fd';

const CARD_SHADOW = Platform.select({
  ios: { shadowColor: '#0b1740', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.08, shadowRadius: 18 },
  android: { elevation: 3 },
  default: {},
});

const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  overdue: { bg: '#fee2e2', fg: '#dc2626' },
  due_soon: { bg: '#fef3c7', fg: '#b45309' },
  paid: { bg: '#dcfce7', fg: '#15803d' },
};

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Morning';
  if (h < 18) return 'Afternoon';
  return 'Evening';
}

function FadeInSection({ children, delay = 0, style }: { children: React.ReactNode; delay?: number; style?: any }) {
  const anim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.spring(anim, { toValue: 1, delay, useNativeDriver: true, speed: 14, bounciness: 4 }).start();
  }, []);
  return (
    <Animated.View
      style={[
        style,
        {
          opacity: anim,
          transform: [
            { translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [16, 0] }) },
            { scale: anim.interpolate({ inputRange: [0, 1], outputRange: [0.97, 1] }) },
          ],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}

function PressScale({ children, onPress, style }: { children: React.ReactNode; onPress?: () => void; style?: any }) {
  const scale = useRef(new Animated.Value(1)).current;
  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => Animated.spring(scale, { toValue: 0.96, useNativeDriver: true, speed: 40, bounciness: 6 }).start()}
      onPressOut={() => Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 30, bounciness: 6 }).start()}
    >
      <Animated.View style={[style, { transform: [{ scale }] }]}>{children}</Animated.View>
    </Pressable>
  );
}

function PulseOrb() {
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 1600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, []);
  const ringScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.18] });
  const ringOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0] });
  const coreScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.05] });
  return (
    <View style={styles.orbWrap}>
      <Animated.View style={[styles.orbRing, { transform: [{ scale: ringScale }], opacity: ringOpacity }]} />
      <Animated.View style={{ transform: [{ scale: coreScale }] }}>
        <View style={styles.orbCore}>
          <View style={styles.orbBars}>
            {[9, 18, 13, 22, 11].map((h, i) => <View key={i} style={[styles.orbBar, { height: h }]} />)}
          </View>
        </View>
      </Animated.View>
    </View>
  );
}

export default function HomeScreen({ navigation, onSignOut }: any) {
  const [customers, setCustomers] = useState<LoanCustomer[]>([]);
  const [loading, setLoading] = useState(true);
  const [convoCount, setConvoCount] = useState<number | null>(null);
  const [showAllCustomers, setShowAllCustomers] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);

  const scrollRef = useRef<ScrollView | null>(null);
  const outboundY = useRef(0);

  useEffect(() => {
    fetchLoanCustomers().then(setCustomers).catch(() => {}).finally(() => setLoading(false));
    fetchOverview().then(d => setConvoCount(d?.total_conversations ?? null)).catch(() => {});
    getStoredUser().then(setUser).catch(() => {});
  }, []);

  function goVoice(callType?: string, customerId?: string, title?: string) {
    navigation.navigate('Voice', { callType, customerId, title: title ?? 'Sonorus' });
  }

  function scrollToOutbound() {
    scrollRef.current?.scrollTo({ y: outboundY.current, animated: true });
  }

  async function handleSignOut() {
    await logout();
    onSignOut?.();
  }

  return (
    <>
    <ScrollView ref={scrollRef} style={styles.root} contentContainerStyle={{ paddingBottom: 48 }}>
      <View style={styles.nav}>
        <View>
          <Text style={styles.greeting}>Good {getGreeting()} 👋</Text>
          <Text style={styles.greetingSub}>Ready when you are.</Text>
        </View>
        <TouchableOpacity style={styles.avatarBtn} onPress={() => setDrawerOpen(true)} hitSlop={10}>
          <View style={styles.hamburgerLine} />
          <View style={styles.hamburgerLine} />
          <View style={[styles.hamburgerLine, { width: 12 }]} />
        </TouchableOpacity>
      </View>

      <FadeInSection delay={0} style={styles.section}>
        <PressScale style={styles.heroCard} onPress={() => goVoice(undefined, undefined, 'Personal Companion')}>
          <LinearGradient colors={[BLUE_LIGHT, BLUE, NAVY]} start={{ x: 0.1, y: 0 }} end={{ x: 1, y: 1 }} style={styles.heroGradient}>
            <View style={styles.heroTextCol}>
              <Text style={styles.heroKicker}>TAP TO TALK</Text>
              <Text style={styles.heroTitle}>Say what's{'\n'}on your mind.</Text>
              <Text style={styles.heroSub}>Sonorus listens, remembers, and actually replies like a person.</Text>
            </View>
            <PulseOrb />
          </LinearGradient>
        </PressScale>
      </FadeInSection>

      <FadeInSection delay={70} style={styles.section}>
        <Text style={styles.sectionHead}>What's the move?</Text>
        <View style={styles.bentoRow}>
          <PressScale style={styles.bentoCard} onPress={() => goVoice('companion', undefined, 'Personal Companion')}>
            <LinearGradient colors={[BLUE_LIGHT, BLUE]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.bentoGradient}>
              <Text style={styles.bentoIcon}>💬</Text>
              <Text style={styles.bentoTitle}>Just talk</Text>
              <Text style={styles.bentoSub}>Companion mode</Text>
            </LinearGradient>
          </PressScale>
          <PressScale style={styles.bentoCard} onPress={scrollToOutbound}>
            <LinearGradient colors={[VIOLET_LIGHT, VIOLET]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.bentoGradient}>
              <Text style={styles.bentoIcon}>📞</Text>
              <Text style={styles.bentoTitle}>Loan reminder</Text>
              <Text style={styles.bentoSub}>Outbound demo</Text>
            </LinearGradient>
          </PressScale>
        </View>
      </FadeInSection>

      {convoCount !== null && (
        <FadeInSection delay={110} style={styles.section}>
          <View style={styles.statsRow}>
            <View style={styles.statBox}>
              <Text style={styles.statBoxNum}>{convoCount}</Text>
              <Text style={styles.statBoxLabel}>Conversations</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statBoxNum}>EN / HI</Text>
              <Text style={styles.statBoxLabel}>Languages</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statBoxNum}>~3s</Text>
              <Text style={styles.statBoxLabel}>Avg. reply</Text>
            </View>
          </View>
        </FadeInSection>
      )}

      <View style={styles.section} onLayout={(e) => { outboundY.current = e.nativeEvent.layout.y; }}>
        <Text style={styles.sectionHead}>Pick someone to call</Text>
        {loading && <ActivityIndicator color={BLUE} style={{ marginVertical: 20 }} />}
        {(showAllCustomers ? customers : customers.slice(0, 4)).map(c => {
          const badge = STATUS_COLORS[c.status] ?? STATUS_COLORS.due_soon;
          return (
            <PressScale key={c.customer_id} style={[styles.custCard, CARD_SHADOW]} onPress={() => goVoice('loan_reminder', c.customer_id, c.name)}>
              <View style={styles.custAvatar}>
                <Text style={styles.custAvatarText}>{c.name.charAt(0)}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.custName}>{c.name}</Text>
                <Text style={styles.custMeta}>{c.loan_type}</Text>
              </View>
              <View style={[styles.statusPill, { backgroundColor: badge.bg }]}>
                <Text style={[styles.statusPillText, { color: badge.fg }]}>{c.status.replace(/_/g, ' ')}</Text>
              </View>
            </PressScale>
          );
        })}
        {!showAllCustomers && customers.length > 4 && (
          <TouchableOpacity onPress={() => setShowAllCustomers(true)} style={styles.viewAllBtn}>
            <Text style={styles.viewAllText}>Show all {customers.length}</Text>
          </TouchableOpacity>
        )}
      </View>

      <Text style={styles.footerNote}>Sonorus · built to actually sound like someone</Text>
    </ScrollView>

    <DrawerMenu
      visible={drawerOpen}
      onClose={() => setDrawerOpen(false)}
      userName={user?.name}
      userEmail={user?.email}
      onNavigate={(screen) => { setDrawerOpen(false); if (screen !== 'Home') navigation.navigate(screen); }}
      onSignOut={() => { setDrawerOpen(false); handleSignOut(); }}
    />
    </>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  nav: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', paddingTop: 58, paddingBottom: 8, paddingHorizontal: 20 },
  greeting: { color: NAVY, fontWeight: '800', fontSize: 24 },
  greetingSub: { color: MUTED, fontSize: 13, marginTop: 4 },
  avatarBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: BG, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: BORDER, gap: 4 },
  hamburgerLine: { width: 18, height: 2, borderRadius: 1, backgroundColor: NAVY },

  section: { paddingHorizontal: 20, marginTop: 22 },
  sectionHead: { color: NAVY, fontWeight: '800', fontSize: 18, marginBottom: 12 },

  heroCard: { borderRadius: 28, overflow: 'hidden' },
  heroGradient: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 24, minHeight: 190 },
  heroTextCol: { flex: 1, paddingRight: 12 },
  heroKicker: { color: 'rgba(255,255,255,0.7)', fontWeight: '800', fontSize: 11, letterSpacing: 1 },
  heroTitle: { color: '#fff', fontWeight: '800', fontSize: 26, marginTop: 10, lineHeight: 31 },
  heroSub: { color: 'rgba(255,255,255,0.8)', fontSize: 13, marginTop: 10, lineHeight: 18 },

  orbWrap: { width: 84, height: 84, alignItems: 'center', justifyContent: 'center' },
  orbRing: { position: 'absolute', width: 84, height: 84, borderRadius: 42, backgroundColor: '#fff' },
  orbCore: {
    width: 64, height: 64, borderRadius: 32, backgroundColor: 'rgba(255,255,255,0.18)', borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.5)',
    alignItems: 'center', justifyContent: 'center',
  },
  orbBars: { flexDirection: 'row', alignItems: 'center', gap: 3, height: 22 },
  orbBar: { width: 3, borderRadius: 2, backgroundColor: '#fff' },

  bentoRow: { flexDirection: 'row', gap: 12 },
  bentoCard: { flex: 1, borderRadius: 22, overflow: 'hidden' },
  bentoGradient: { padding: 18, minHeight: 128, justifyContent: 'flex-end' },
  bentoIcon: { fontSize: 24, marginBottom: 10 },
  bentoTitle: { color: '#fff', fontWeight: '800', fontSize: 16 },
  bentoSub: { color: 'rgba(255,255,255,0.8)', fontSize: 11, marginTop: 3, fontWeight: '600' },

  statsRow: { flexDirection: 'row', gap: 10 },
  statBox: { flex: 1, backgroundColor: BG, borderRadius: 16, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: BORDER },
  statBoxNum: { color: NAVY, fontWeight: '800', fontSize: 16 },
  statBoxLabel: { color: MUTED, fontSize: 10, fontWeight: '700', marginTop: 3, textAlign: 'center' },

  custCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 16, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: BORDER },
  custAvatar: { width: 42, height: 42, borderRadius: 21, backgroundColor: BLUE, alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  custAvatarText: { color: '#fff', fontWeight: '800', fontSize: 16 },
  custName: { color: NAVY, fontWeight: '700', fontSize: 14.5 },
  custMeta: { color: MUTED, fontSize: 12, marginTop: 2 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20 },
  statusPillText: { fontSize: 10, fontWeight: '800', textTransform: 'capitalize' },
  viewAllBtn: { alignItems: 'center', paddingVertical: 10 },
  viewAllText: { color: BLUE, fontWeight: '700', fontSize: 13 },

  footerNote: { color: MUTED, fontSize: 11, textAlign: 'center', marginTop: 32 },
});
