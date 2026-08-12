import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { login, signup } from '../auth';

const NAVY = '#0b1740';
const BLUE = '#2f5bff';
const BLUE_LIGHT = '#7c9bff';
const MUTED = '#5b6478';
const BORDER = '#e6e9f2';

export default function LoginScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setError(null);
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }
    if (mode === 'signup' && !name.trim()) {
      setError('Enter your name.');
      return;
    }
    setLoading(true);
    try {
      if (mode === 'signup') {
        await signup(email.trim(), password, name.trim());
      } else {
        await login(email.trim(), password);
      }
      onAuthenticated();
    } catch (e: any) {
      setError(e?.message || 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.orbWrap}>
          <LinearGradient colors={[BLUE_LIGHT, BLUE, NAVY]} start={{ x: 0.2, y: 0 }} end={{ x: 1, y: 1 }} style={styles.orb}>
            <View style={styles.orbBars}>
              {[10, 20, 14, 24, 12].map((h, i) => <View key={i} style={[styles.orbBar, { height: h }]} />)}
            </View>
          </LinearGradient>
        </View>

        <Text style={styles.title}>Sonorus</Text>
        <Text style={styles.subtitle}>{mode === 'login' ? 'Welcome back.' : 'Create your account.'}</Text>

        <View style={styles.form}>
          {mode === 'signup' && (
            <View style={styles.field}>
              <Text style={styles.label}>Name</Text>
              <TextInput
                style={styles.input}
                value={name}
                onChangeText={setName}
                placeholder="Your name"
                placeholderTextColor="#a3aabf"
                autoCapitalize="words"
              />
            </View>
          )}

          <View style={styles.field}>
            <Text style={styles.label}>Email</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor="#a3aabf"
              autoCapitalize="none"
              keyboardType="email-address"
              autoCorrect={false}
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder={mode === 'signup' ? 'At least 6 characters' : 'Your password'}
              placeholderTextColor="#a3aabf"
              secureTextEntry
            />
          </View>

          {error && <Text style={styles.error}>{error}</Text>}

          <TouchableOpacity style={styles.submitBtn} onPress={submit} disabled={loading}>
            {loading ? <ActivityIndicator color="#fff" /> : (
              <Text style={styles.submitBtnText}>{mode === 'login' ? 'Log in' : 'Sign up'}</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity style={styles.switchRow} onPress={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(null); }}>
            <Text style={styles.switchText}>
              {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
              <Text style={styles.switchLink}>{mode === 'login' ? 'Sign up' : 'Log in'}</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  scroll: { flexGrow: 1, alignItems: 'center', paddingHorizontal: 28, paddingTop: 90, paddingBottom: 40 },
  orbWrap: { width: 88, height: 88, borderRadius: 44, alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  orb: {
    width: 88, height: 88, borderRadius: 44, alignItems: 'center', justifyContent: 'center',
    shadowColor: BLUE, shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.35, shadowRadius: 18, elevation: 8,
  },
  orbBars: { flexDirection: 'row', alignItems: 'center', gap: 3, height: 24 },
  orbBar: { width: 3, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.9)' },
  title: { color: NAVY, fontWeight: '800', fontSize: 26 },
  subtitle: { color: MUTED, fontSize: 14, marginTop: 6, marginBottom: 30 },
  form: { width: '100%' },
  field: { marginBottom: 16 },
  label: { color: NAVY, fontWeight: '700', fontSize: 12, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: BORDER, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 13, fontSize: 15, color: NAVY, backgroundColor: '#f6f8fc' },
  error: { color: '#dc2626', fontSize: 13, marginBottom: 12, textAlign: 'center' },
  submitBtn: { backgroundColor: BLUE, borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 6 },
  submitBtnText: { color: '#fff', fontWeight: '800', fontSize: 15 },
  switchRow: { marginTop: 20, alignItems: 'center' },
  switchText: { color: MUTED, fontSize: 13 },
  switchLink: { color: BLUE, fontWeight: '800' },
});
