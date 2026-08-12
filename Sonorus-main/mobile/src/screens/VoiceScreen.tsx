import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Animated, Easing, Pressable, Alert } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import {
  useAudioRecorder,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  createAudioPlayer,
  AudioPlayer,
} from 'expo-audio';
import { createMobileSession, sendTurn, endMobileSession, base64WavToLocalUri } from '../api';

const NAVY = '#0b1740';
const NAVY_DEEP = '#050a20';
const BLUE = '#2f5bff';
const BLUE_LIGHT = '#7c9bff';
const RED = '#ff5470';

type CallState = 'connecting' | 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

interface TranscriptEntry { role: 'user' | 'agent'; text: string; }

const STATE_LABEL: Record<CallState, string> = {
  connecting: 'Connecting…',
  idle: 'Tap to talk',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Sonorus is speaking…',
  error: "Didn't catch that — tap to try again",
};

function CallOrb({ state, onPress }: { state: CallState; onPress: () => void }) {
  const pulse = useRef(new Animated.Value(0)).current;
  const spin = useRef(new Animated.Value(0)).current;
  const bars = useRef([0, 1, 2, 3, 4].map(() => new Animated.Value(0.3))).current;

  useEffect(() => {
    pulse.stopAnimation();
    spin.stopAnimation();
    bars.forEach(b => b.stopAnimation());

    if (state === 'idle' || state === 'connecting') {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1, duration: 1900, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 0, duration: 1900, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        ])
      );
      loop.start();
      return () => loop.stop();
    }
    if (state === 'listening') {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1, duration: 550, easing: Easing.out(Easing.quad), useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 0, duration: 550, easing: Easing.in(Easing.quad), useNativeDriver: true }),
        ])
      );
      loop.start();
      return () => loop.stop();
    }
    if (state === 'thinking') {
      const loop = Animated.loop(
        Animated.timing(spin, { toValue: 1, duration: 1100, easing: Easing.linear, useNativeDriver: true })
      );
      loop.start();
      return () => loop.stop();
    }
    if (state === 'speaking') {
      const anims = bars.map((b, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.timing(b, { toValue: 1, duration: 260 + i * 40, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
            Animated.timing(b, { toValue: 0.3, duration: 260 + i * 40, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
          ])
        )
      );
      anims.forEach(a => a.start());
      return () => anims.forEach(a => a.stop());
    }
  }, [state]);

  const ringScale = pulse.interpolate({ inputRange: [0, 1], outputRange: state === 'listening' ? [1, 1.22] : [1, 1.1] });
  const ringOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: state === 'listening' ? [0.5, 0] : [0.4, 0.06] });
  const coreScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, state === 'listening' ? 1.06 : 1.04] });
  const spinDeg = spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });

  const accent = state === 'listening' ? [RED, '#c92a4a', NAVY_DEEP] : [BLUE_LIGHT, BLUE, NAVY_DEEP];

  return (
    <Pressable onPress={onPress} hitSlop={20}>
      <View style={styles.orbWrap}>
        <Animated.View style={[styles.orbRingOuter, { transform: [{ scale: ringScale }], opacity: ringOpacity, borderColor: state === 'listening' ? RED : BLUE_LIGHT }]} />
        <Animated.View style={[styles.orbRingInner, { transform: [{ scale: ringScale }], opacity: ringOpacity, borderColor: state === 'listening' ? RED : BLUE_LIGHT }]} />
        <Animated.View style={{ transform: [{ scale: coreScale }] }}>
          <LinearGradient colors={accent as any} start={{ x: 0.15, y: 0 }} end={{ x: 1, y: 1 }} style={styles.orbCore}>
            {state === 'thinking' ? (
              <Animated.View style={[styles.thinkRing, { transform: [{ rotate: spinDeg }] }]} />
            ) : state === 'speaking' ? (
              <View style={styles.orbBars}>
                {bars.map((b, i) => (
                  <Animated.View
                    key={i}
                    style={[
                      styles.orbBar,
                      { transform: [{ scaleY: b }] },
                    ]}
                  />
                ))}
              </View>
            ) : (
              <View style={styles.micGlyph}>
                <View style={styles.micGlyphBody} />
                <View style={styles.micGlyphBase} />
              </View>
            )}
          </LinearGradient>
        </Animated.View>
      </View>
    </Pressable>
  );
}

export default function VoiceScreen({ route, navigation }: any) {
  const { callType, customerId, title } = route.params ?? {};
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [callState, setCallState] = useState<CallState>('connecting');
  const [isBusy, setIsBusy] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const playerRef = useRef<AudioPlayer | null>(null);
  const scrollRef = useRef<ScrollView | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const { granted } = await requestRecordingPermissionsAsync();
      if (!granted) {
        Alert.alert('Microphone permission needed', 'Sonorus needs mic access to hear you.');
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      try {
        const res = await createMobileSession(callType, customerId);
        if (!mounted) return;
        sessionIdRef.current = res.session_id;
        setSessionId(res.session_id);
        setCallState('idle');
        if (res.opening_text) {
          setTranscript([{ role: 'agent', text: res.opening_text }]);
        }
        if (res.opening_audio_b64) {
          await playReply(res.opening_audio_b64);
        }
      } catch (e) {
        setCallState('error');
      }
    })();
    return () => {
      mounted = false;
      playerRef.current?.remove();
      if (sessionIdRef.current) endMobileSession(sessionIdRef.current);
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [transcript]);

  async function playReply(b64: string) {
    const uri = await base64WavToLocalUri(b64);
    playerRef.current?.remove();
    const player = createAudioPlayer(uri);
    playerRef.current = player;
    setCallState('speaking');
    player.addListener('playbackStatusUpdate', (s: any) => {
      if (s.didJustFinish) {
        setCallState('idle');
        player.remove();
        if (playerRef.current === player) playerRef.current = null;
      }
    });
    player.play();
  }

  async function startRecording() {
    if (isBusy) return;
    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
      setCallState('listening');
    } catch (e) {
      Alert.alert('Mic error', String(e));
    }
  }

  async function stopRecording() {
    setIsBusy(true);
    setCallState('thinking');
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri || !sessionId) return;

      const result = await sendTurn(sessionId, uri, 'audio/m4a');
      if (!result.transcript) {
        setCallState('error');
        setIsBusy(false);
        return;
      }
      setTranscript(prev => [...prev, { role: 'user', text: result.transcript }, { role: 'agent', text: result.reply_text }]);
      if (result.reply_audio_b64) {
        await playReply(result.reply_audio_b64);
      } else {
        setCallState('idle');
      }
    } catch (e) {
      setCallState('error');
    } finally {
      setIsBusy(false);
    }
  }

  function handleOrbPress() {
    if (isBusy || !sessionId) return;
    if (callState === 'listening') stopRecording();
    else if (callState === 'idle' || callState === 'error') startRecording();
  }

  return (
    <LinearGradient colors={[NAVY, NAVY_DEEP]} style={styles.root}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={12}>
          <Text style={styles.back}>‹ End</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{title || 'Sonorus'}</Text>
        <View style={{ width: 44 }} />
      </View>

      <View style={styles.orbSection}>
        <CallOrb state={callState} onPress={handleOrbPress} />
        <Text style={styles.stateLabel}>{STATE_LABEL[callState]}</Text>
      </View>

      <ScrollView ref={scrollRef} style={styles.transcript} contentContainerStyle={{ padding: 16, paddingBottom: 32 }}>
        {transcript.length === 0 && callState !== 'connecting' && (
          <Text style={styles.empty}>Tap the orb and start talking.</Text>
        )}
        {transcript.map((t, i) => (
          <View key={i} style={[styles.bubble, t.role === 'user' ? styles.bubbleUser : styles.bubbleAgent]}>
            <Text style={styles.bubbleSpeaker}>{t.role === 'user' ? 'You' : 'Sonorus'}</Text>
            <Text style={styles.bubbleText}>{t.text}</Text>
          </View>
        ))}
      </ScrollView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 55, paddingBottom: 8, paddingHorizontal: 18 },
  back: { color: 'rgba(255,255,255,0.85)', fontWeight: '700', fontSize: 15, width: 44 },
  headerTitle: { color: '#fff', fontWeight: '800', fontSize: 16 },

  orbSection: { alignItems: 'center', paddingTop: 28, paddingBottom: 18 },
  stateLabel: { color: 'rgba(255,255,255,0.75)', fontSize: 14, fontWeight: '700', marginTop: 22, letterSpacing: 0.3 },

  orbWrap: { width: 176, height: 176, alignItems: 'center', justifyContent: 'center' },
  orbRingOuter: { position: 'absolute', width: 176, height: 176, borderRadius: 88, borderWidth: 1.5 },
  orbRingInner: { position: 'absolute', width: 140, height: 140, borderRadius: 70, borderWidth: 1.5 },
  orbCore: {
    width: 108, height: 108, borderRadius: 54, alignItems: 'center', justifyContent: 'center',
    shadowColor: BLUE, shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.5, shadowRadius: 26, elevation: 12,
  },
  orbBars: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 34 },
  orbBar: { width: 5, height: 34, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.95)' },
  thinkRing: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 3,
    borderColor: 'rgba(255,255,255,0.25)', borderTopColor: '#fff',
  },
  micGlyph: { alignItems: 'center' },
  micGlyphBody: { width: 16, height: 26, borderRadius: 8, backgroundColor: 'rgba(255,255,255,0.95)' },
  micGlyphBase: { width: 26, height: 3, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.95)', marginTop: 6 },

  transcript: { flex: 1 },
  empty: { color: 'rgba(255,255,255,0.4)', textAlign: 'center', marginTop: 20, fontSize: 13 },
  bubble: { maxWidth: '84%', padding: 13, borderRadius: 16, marginBottom: 12 },
  bubbleUser: { alignSelf: 'flex-end', backgroundColor: 'rgba(47,91,255,0.22)', borderWidth: 1, borderColor: 'rgba(124,155,255,0.35)' },
  bubbleAgent: { alignSelf: 'flex-start', backgroundColor: 'rgba(255,255,255,0.07)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.12)' },
  bubbleSpeaker: { fontSize: 10, fontWeight: '800', color: 'rgba(255,255,255,0.55)', textTransform: 'uppercase', marginBottom: 4, letterSpacing: 0.5 },
  bubbleText: { color: '#fff', fontSize: 14, lineHeight: 20 },
});
