import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Animated, Modal, Pressable, Dimensions, Easing } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

const { width: SCREEN_W } = Dimensions.get('window');
const DRAWER_W = Math.min(300, SCREEN_W * 0.8);

const NAVY = '#0b1740';
const NAVY_DEEP = '#050a20';
const BLUE = '#2f5bff';
const MUTED = '#5b6478';
const BORDER = '#ece9fb';

type DrawerScreen = 'Home' | 'About' | 'CallHistory' | 'KnowledgeBase' | 'Dashboard';

interface DrawerMenuProps {
  visible: boolean;
  onClose: () => void;
  userName?: string;
  userEmail?: string;
  onNavigate: (screen: DrawerScreen) => void;
  onSignOut: () => void;
}

export default function DrawerMenu({ visible, onClose, userName, userEmail, onNavigate, onSignOut }: DrawerMenuProps) {
  const [mounted, setMounted] = useState(visible);
  const translateX = useRef(new Animated.Value(-DRAWER_W)).current;
  const backdropOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.parallel([
        Animated.spring(translateX, { toValue: 0, useNativeDriver: true, speed: 16, bounciness: 4 }),
        Animated.timing(backdropOpacity, { toValue: 1, duration: 220, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(translateX, { toValue: -DRAWER_W, duration: 200, easing: Easing.in(Easing.quad), useNativeDriver: true }),
        Animated.timing(backdropOpacity, { toValue: 0, duration: 180, useNativeDriver: true }),
      ]).start(() => setMounted(false));
    }
  }, [visible]);

  if (!mounted) return null;

  return (
    <Modal transparent visible={mounted} animationType="none" onRequestClose={onClose}>
      <View style={StyleSheet.absoluteFill}>
        <Animated.View style={[StyleSheet.absoluteFill, styles.backdrop, { opacity: backdropOpacity }]}>
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        </Animated.View>

        <Animated.View style={[styles.drawer, { transform: [{ translateX }] }]}>
          <LinearGradient colors={[NAVY, NAVY_DEEP]} style={styles.drawerHeader}>
            <View style={styles.avatarCircle}>
              <Text style={styles.avatarText}>{(userName || 'S').charAt(0).toUpperCase()}</Text>
            </View>
            <Text style={styles.userName} numberOfLines={1}>{userName || 'Sonorus User'}</Text>
            <Text style={styles.userEmail} numberOfLines={1}>{userEmail || ''}</Text>
          </LinearGradient>

          <View style={styles.menuList}>
            <MenuRow icon="🏠" label="Home" onPress={() => onNavigate('Home')} />
            <MenuRow icon="🕓" label="Call History" onPress={() => onNavigate('CallHistory')} />
            <MenuRow icon="📚" label="Knowledge Base" onPress={() => onNavigate('KnowledgeBase')} />
            <MenuRow icon="📊" label="Dashboard" onPress={() => onNavigate('Dashboard')} />
            <MenuRow icon="✨" label="About Sonorus" onPress={() => onNavigate('About')} />
          </View>

          <View style={{ flex: 1 }} />

          <TouchableOpacity style={styles.signOutBtn} onPress={onSignOut}>
            <Text style={styles.signOutIcon}>⏻</Text>
            <Text style={styles.signOutText}>Sign out</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>
    </Modal>
  );
}

function MenuRow({ icon, label, onPress }: { icon: string; label: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.menuItem} onPress={onPress}>
      <Text style={styles.menuIcon}>{icon}</Text>
      <Text style={styles.menuText}>{label}</Text>
      <Text style={styles.menuChevron}>›</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  backdrop: { backgroundColor: 'rgba(5,10,32,0.55)' },
  drawer: {
    position: 'absolute', top: 0, bottom: 0, left: 0, width: DRAWER_W, backgroundColor: '#fff',
    shadowColor: '#000', shadowOffset: { width: 4, height: 0 }, shadowOpacity: 0.2, shadowRadius: 20, elevation: 16,
  },
  drawerHeader: { paddingTop: 64, paddingBottom: 24, paddingHorizontal: 22 },
  avatarCircle: {
    width: 56, height: 56, borderRadius: 28, backgroundColor: 'rgba(255,255,255,0.14)', borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.35)',
    alignItems: 'center', justifyContent: 'center', marginBottom: 12,
  },
  avatarText: { color: '#fff', fontWeight: '800', fontSize: 22 },
  userName: { color: '#fff', fontWeight: '800', fontSize: 16 },
  userEmail: { color: 'rgba(255,255,255,0.6)', fontSize: 12, marginTop: 3 },

  menuList: { paddingTop: 14, paddingHorizontal: 10 },
  menuItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 12, borderRadius: 12 },
  menuIcon: { fontSize: 18, marginRight: 14, width: 22, textAlign: 'center' },
  menuText: { flex: 1, color: NAVY, fontWeight: '700', fontSize: 14.5 },
  menuChevron: { color: '#c7cbe0', fontSize: 18, fontWeight: '700' },

  signOutBtn: { flexDirection: 'row', alignItems: 'center', paddingVertical: 16, paddingHorizontal: 22, borderTopWidth: 1, borderTopColor: BORDER },
  signOutIcon: { fontSize: 16, marginRight: 14, width: 22, textAlign: 'center', color: '#dc2626' },
  signOutText: { color: '#dc2626', fontWeight: '700', fontSize: 14.5 },
});
