# SolarEdge Portal Live

Intégration personnalisée Home Assistant pour lire en direct la puissance solaire, la consommation et les échanges avec le réseau depuis le portail SolarEdge.

## Installation avec HACS

Home Assistant 2026.8.2 ou ultérieur et HACS doivent être installés.

1. Ouvre **HACS → ⋮ → Dépôts personnalisés**.
2. Ajoute le [dépôt SolarEdge Portal Live](https://github.com/philippec78/SolarEdge-Portal-Live) dans la catégorie **Intégration**.
3. Dans HACS, cherche **SolarEdge Portal Live**, télécharge l’intégration et redémarre Home Assistant.
4. Dans **Paramètres → Appareils et services → Ajouter une intégration**, sélectionne **SolarEdge Portal Live**.
5. Saisis l’adresse e-mail et le mot de passe de ton compte SolarEdge, puis l’identifiant du site visible dans l’adresse du tableau de bord après `siteId=`. L’intervalle de lecture est de 30 secondes par défaut et se règle entre 15 et 120 secondes.

Entre le lever et le coucher du soleil, l’intégration utilise l’intervalle de jour configuré. La nuit, elle interroge SolarEdge toutes les 15 minutes par défaut. Pour changer cet intervalle, ouvre **Paramètres → Appareils et services → SolarEdge Portal Live → Configurer** et choisis une valeur de 1 à 120 minutes. Home Assistant recharge l’intégration en enregistrant ce réglage. Les horaires de lever et de coucher suivent la localisation configurée dans Home Assistant.

## Entités

| Entité | Mesure |
| --- | --- |
| Puissance réseau | Watts positifs à l’import et négatifs à l’injection |
| Puissance importée | Watts importés du réseau |
| Puissance injectée | Watts injectés sur le réseau |
| Puissance solaire | Production instantanée en watts |
| Puissance consommée | Consommation instantanée du site en watts |
| Dernier relevé | Horodatage fourni par SolarEdge |

Les capteurs de puissance deviennent indisponibles si la lecture échoue, si SolarEdge signale que le direct est indisponible ou si le relevé a plus de deux minutes.

## Connexion SolarEdge

Home Assistant conserve le mot de passe et le jeton de renouvellement dans la configuration locale de l’intégration. Les sauvegardes de configuration peuvent les contenir. Le module renouvelle automatiquement le jeton d’accès. Si SolarEdge refuse le jeton de renouvellement, il tente une nouvelle connexion. Si le portail exige une vérification interactive, Home Assistant demande une réauthentification.

Le flux utilisé est celui du portail SolarEdge et peut évoluer. La connexion et le renouvellement ont été observés dans Firefox. L’accès avec le module reste à valider sur une instance Home Assistant connectée au compte réel. Le projet est indépendant de SolarEdge. Le parcours de connexion est également documenté dans le projet [SolarEdge Cloud](https://github.com/digital-homesteaders/ha-solaredge).
